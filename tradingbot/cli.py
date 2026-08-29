"""Command line interface.

Subcommands:
  backtest  replay a strategy over historical data
  paper     run the live loop against real prices with simulated money
  live      run the live loop with real money (guarded, see `_confirm_live`)
  fetch     download and cache OHLCV history
  serve     run the CBot web dashboard
  research  review a token contract address before you trade it
  optimize  grid-search strategy parameters over historical data
  strategies / status  introspection helpers
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .backtest import Backtester
from .config import Config, ConfigError, from_dict, load_config
from .data import csv_store, generate_synthetic, load_history
from .engine import TradingEngine
from .exchange.paper import PaperBroker
from .logging_setup import setup_logging
from .metrics import format_report
from .models import Candle
from .notifier import Notifier
from .state import load_state, state_path
from .strategies import available_strategies, get_strategy, strategy_class

log = logging.getLogger(__name__)

LIVE_CONFIRMATION = "TRADE REAL MONEY"


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def _resolve_config(args) -> Config:
    if args.config:
        config = load_config(args.config)
    else:
        config = from_dict({})
        log.warning("no --config given; using built-in defaults (paper mode, BTC/USDT 1h)")

    if getattr(args, "symbol", None):
        config.symbols = [args.symbol]
    if getattr(args, "timeframe", None):
        config.timeframe = args.timeframe
    if getattr(args, "cash", None):
        config.execution.starting_cash = args.cash
    if getattr(args, "log_level", None):
        config.log_level = args.log_level
    if getattr(args, "poll_interval", None):
        config.execution.poll_interval = args.poll_interval
    config.validate()
    return config


def _resolve_strategy(args, config: Config):
    name = getattr(args, "strategy", None) or config.strategy.name
    params = dict(config.strategy.params) if name == config.strategy.name else {}
    params.update(_parse_params(getattr(args, "param", None) or []))
    try:
        return get_strategy(name, **params)
    except KeyError as exc:
        raise SystemExit(f"error: {exc.args[0]}")
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")


def _parse_params(pairs: list[str]) -> dict:
    """Parse `--param fast_period=10` arguments, inferring value types."""
    out = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"error: --param expects key=value, got {pair!r}")
        key, _, raw = pair.partition("=")
        out[key.strip()] = _coerce(raw.strip())
    return out


def _coerce(raw: str):
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("none", "null"):
        return None
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            continue
    return raw


def _get_candles(args, config: Config, symbol: str) -> list[Candle]:
    if getattr(args, "synthetic", False):
        log.warning("using SYNTHETIC data — results are meaningless for strategy selection")
        return generate_synthetic(bars=args.bars, timeframe=config.timeframe, seed=args.seed)
    return load_history(
        symbol,
        config.timeframe,
        data_dir=config.data_dir,
        csv_path=getattr(args, "csv", None),
        exchange_config=config.exchange if getattr(args, "download", False) else None,
        days=getattr(args, "days", 365),
    )


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
def cmd_backtest(args) -> int:
    config = _resolve_config(args)
    strategy = _resolve_strategy(args, config)

    exit_code = 0
    for symbol in config.symbols:
        try:
            candles = _get_candles(args, config, symbol)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        result = Backtester(config, strategy).run(symbol, candles)
        print(format_report(result.metrics, f"{symbol} — {result.strategy}"))

        if result.rejections:
            print("  Entries skipped by the risk manager:")
            for reason, count in sorted(result.rejections.items(), key=lambda kv: -kv[1]):
                print(f"    {count:>4}x  {reason}")
            print()
        if result.halted_reason:
            print(f"  !! Trading halted mid-run: {result.halted_reason}\n")

        if args.json:
            payload = {
                "symbol": symbol,
                "strategy": result.strategy,
                "metrics": result.metrics.as_dict(),
                "trades": [
                    {
                        "opened_at": t.opened_at.isoformat(),
                        "closed_at": t.closed_at.isoformat(),
                        "side": t.side.value,
                        "amount": t.amount,
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "net_pnl": t.net_pnl,
                        "reason": t.reason,
                    }
                    for t in result.trades
                ],
            }
            Path(args.json).write_text(json.dumps(payload, indent=2, default=str))
            print(f"  Wrote {args.json}\n")

        if args.equity_csv:
            path = Path(args.equity_csv)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w") as fh:
                fh.write("timestamp,equity,cash,position_value\n")
                for p in result.equity_curve:
                    fh.write(f"{p.timestamp.isoformat()},{p.equity},{p.cash},{p.position_value}\n")
            print(f"  Wrote {path}\n")

    return exit_code


def cmd_optimize(args) -> int:
    """Grid-search strategy parameters. Treat the winner with suspicion."""
    config = _resolve_config(args)
    name = args.strategy or config.strategy.name
    grid = {}
    for pair in args.grid:
        key, _, raw = pair.partition("=")
        grid[key.strip()] = [_coerce(v.strip()) for v in raw.split(",")]
    if not grid:
        raise SystemExit("error: --grid is required, e.g. --grid fast_period=5,10,20")

    symbol = config.symbols[0]
    candles = _get_candles(args, config, symbol)

    keys = sorted(grid)
    rows = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = dict(zip(keys, combo))
        try:
            strategy = get_strategy(name, **params)
            result = Backtester(config, strategy).run(symbol, candles)
        except (ValueError, KeyError) as exc:
            log.debug("skipping %s: %s", params, exc)
            continue
        rows.append((params, result.metrics))

    if not rows:
        print("no valid parameter combinations", file=sys.stderr)
        return 1

    key_fn = {
        "sharpe": lambda m: m.sharpe_ratio,
        "return": lambda m: m.total_return_pct,
        "calmar": lambda m: m.calmar_ratio,
        "profit_factor": lambda m: m.profit_factor,
    }[args.sort]
    rows.sort(key=lambda row: key_fn(row[1]), reverse=True)

    print(f"\n  Grid search: {name} on {symbol} ({len(rows)} combinations, sorted by {args.sort})\n")
    header = f"  {'params':<44} {'return%':>9} {'sharpe':>8} {'maxDD%':>8} {'trades':>7} {'win%':>7}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for params, m in rows[: args.top]:
        label = ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
        print(
            f"  {label:<44} {m.total_return_pct:>9.2f} {m.sharpe_ratio:>8.2f} "
            f"{m.max_drawdown_pct:>8.2f} {m.total_trades:>7} {m.win_rate:>7.1f}"
        )
    print(
        "\n  Note: the best row here is the best fit to THIS data. Validate it on a "
        "held-out period before trusting it.\n"
    )
    return 0


def cmd_paper(args) -> int:
    config = _resolve_config(args)
    config.execution.mode = "paper"
    strategy = _resolve_strategy(args, config)

    data_source = None
    if not args.synthetic:
        from .exchange.ccxt_adapter import CcxtBroker, ExchangeError

        try:
            data_source = CcxtBroker(config.exchange, allow_trading=False)
        except ExchangeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        data_source = _SyntheticSource(config, args.seed)

    broker = PaperBroker(
        starting_cash=config.execution.starting_cash,
        fee_rate=config.execution.fee_rate,
        slippage_pct=config.execution.slippage_pct,
        data_source=data_source,
    )
    engine = TradingEngine(config, strategy, broker, Notifier())
    print(
        f"\n  PAPER trading {', '.join(config.symbols)} @ {config.timeframe} "
        f"with {strategy.describe()}\n  Simulated cash: {config.execution.starting_cash:,.2f}. "
        f"Ctrl-C to stop.\n"
    )
    engine.run(max_iterations=args.iterations)
    return 0


def cmd_live(args) -> int:
    config = _resolve_config(args)
    config.execution.mode = "live"
    strategy = _resolve_strategy(args, config)

    if not _confirm_live(config, args):
        return 1

    from .exchange.ccxt_adapter import CcxtBroker, ExchangeError

    try:
        broker = CcxtBroker(config.exchange, allow_trading=True)
    except ExchangeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    engine = TradingEngine(config, strategy, broker, Notifier())
    engine.run(max_iterations=args.iterations)
    return 0


def _confirm_live(config: Config, args) -> bool:
    """Three independent locks stand between a typo and a real order."""
    if not config.execution.confirm_live:
        print(
            "refusing to trade live: set `execution.confirm_live: true` in your config "
            "to acknowledge that real orders will be placed.",
            file=sys.stderr,
        )
        return False

    if not args.i_understand_the_risk:
        print(
            "refusing to trade live: pass --i-understand-the-risk to confirm you accept "
            "that this bot can lose real money.",
            file=sys.stderr,
        )
        return False

    venue = "TESTNET" if config.exchange.testnet else "PRODUCTION (real funds)"
    print(f"\n  About to trade LIVE on {config.exchange.name} — {venue}")
    print(f"  Symbols:  {', '.join(config.symbols)} @ {config.timeframe}")
    print(f"  Strategy: {strategy_summary(config, args)}")
    print(f"  Risk:     {config.risk.risk_per_trade:.2%}/trade, "
          f"max drawdown {config.risk.max_drawdown_pct:.0%}, "
          f"daily loss cap {config.risk.max_daily_loss_pct:.0%}")

    if config.exchange.testnet or args.yes:
        return True

    # Real funds and a real terminal: require a typed phrase, not just "y".
    if not sys.stdin.isatty():
        print(
            "refusing to trade live with real funds from a non-interactive shell; "
            "pass --yes only if you genuinely intend that.",
            file=sys.stderr,
        )
        return False

    typed = input(f"\n  Type '{LIVE_CONFIRMATION}' to proceed: ").strip()
    if typed != LIVE_CONFIRMATION:
        print("aborted.", file=sys.stderr)
        return False
    return True


def strategy_summary(config: Config, args) -> str:
    name = getattr(args, "strategy", None) or config.strategy.name
    return name


def cmd_fetch(args) -> int:
    config = _resolve_config(args)
    from .data.feed import download

    for symbol in config.symbols:
        candles = download(
            symbol, config.timeframe, config.exchange, days=args.days, data_dir=config.data_dir
        )
        path = csv_store.cache_path(config.data_dir, symbol, config.timeframe)
        span = f"{candles[0].timestamp:%Y-%m-%d} to {candles[-1].timestamp:%Y-%m-%d}" if candles else "empty"
        print(f"  {symbol} {config.timeframe}: {len(candles)} candles ({span}) -> {path}")
    return 0


def cmd_strategies(args) -> int:
    print("\n  Available strategies\n")
    for name in available_strategies():
        cls = strategy_class(name)
        doc = (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else ""
        print(f"  {name}\n      {doc}")
        for key, value in sorted(cls.default_params.items()):
            print(f"        {key:<22} default: {value}")
        print()
    return 0


def cmd_status(args) -> int:
    config = _resolve_config(args)
    path = state_path(config.state_dir)
    saved = load_state(path)
    if not saved:
        print(f"  no saved state at {path}")
        return 0

    print(f"\n  State file: {path}")
    print(f"  Updated:    {saved.get('updated_at')}")
    print(f"  Cash:       {saved.get('cash', 0):,.2f}")
    print(f"  Peak equity:{saved.get('peak_equity', 0):>12,.2f}")
    print(f"  Realized today: {saved.get('realized_today', 0):,.2f}")
    if saved.get("halted_reason"):
        print(f"  HALTED:     {saved['halted_reason']}")

    positions = saved.get("positions", {})
    if not positions:
        print("  Positions:  none\n")
        return 0
    print("  Positions:")
    for symbol, p in positions.items():
        print(
            f"    {symbol:<12} {p.side.value:<5} {p.amount:.6f} @ {p.entry_price:,.2f} "
            f"stop={p.stop_price} tp={p.take_profit_price}"
        )
    print()
    return 0


def cmd_serve(args) -> int:
    config = _resolve_config(args)
    from .web import serve

    serve(config, host=args.host, port=args.port)
    return 0


SEVERITY_MARKS = {
    "critical": "!!", "high": "! ", "medium": "~ ", "low": ". ", "good": "+ ", "info": "  ",
}


def cmd_research(args) -> int:
    """Review a token contract address for the powers it grants and who holds them."""
    from .research import ContractResearcher, SourceError, is_address, normalise_chain

    if not is_address(args.address):
        print(f"error: {args.address!r} is not a valid contract address "
              f"(expected 0x followed by 40 hex characters)", file=sys.stderr)
        return 1

    try:
        chain = normalise_chain(args.chain)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        report = ContractResearcher(chain).review(args.address, deployer_limit=args.max_deployments)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        Path(args.json).write_text(json.dumps(report.as_dict(), indent=2, default=str))
        print(f"  Wrote {args.json}")
        if not args.print_report:
            return 0

    _print_report(report)
    return 0


def _print_report(report) -> None:
    facts = report.facts
    label = facts.token_name or facts.name or "unknown contract"
    symbol = f" ({facts.token_symbol})" if facts.token_symbol else ""

    print()
    print(f"  {label}{symbol}")
    print(f"  {'=' * 62}")
    print(f"  Address        {report.address}")
    print(f"  Chain          {report.chain}")
    print(f"  Risk           {report.risk_score}/100 — {report.risk_band.upper()}")
    print(f"  Verified       {'yes' if facts.verified else 'NO — source not published'}")
    if facts.created_at:
        age = facts.age_days or 0
        print(f"  Deployed       {facts.created_at:%Y-%m-%d} ({age:.0f} days ago)")
    if facts.owner is not None:
        state = "renounced" if facts.ownership_renounced else facts.owner
        print(f"  Owner          {state}")
    if facts.is_proxy:
        print(f"  Proxy          yes — implementation {facts.implementation or 'unknown'}")
    if facts.total_supply and facts.decimals is not None:
        try:
            supply = int(facts.total_supply) / (10 ** facts.decimals)
            print(f"  Total supply   {supply:,.0f}")
        except (ValueError, ZeroDivisionError):
            pass

    print()
    print("  Findings")
    print(f"  {'-' * 62}")
    for finding in report.by_severity():
        mark = SEVERITY_MARKS.get(finding.severity.value, "  ")
        print(f"  {mark} {finding.title}")
        for line in _wrap(finding.detail, 66):
            print(f"       {line}")
        if finding.evidence:
            print(f"       evidence: {finding.evidence[:100]}")
        print()

    deployer = report.deployer
    if deployer.address:
        print("  Deployer")
        print(f"  {'-' * 62}")
        print(f"  Address        {deployer.address}")
        if deployer.first_seen:
            print(f"  First seen     {deployer.first_seen:%Y-%m-%d}")
        if deployer.funded_by:
            print(f"  Funded by      {deployer.funded_by}")

        others = [d for d in deployer.deployed_contracts
                  if d.get("address", "").lower() != report.address.lower()]
        if others:
            print(f"  Past projects  {len(others)} other contract(s) from this address:")
            for item in others[:15]:
                when = item.get("timestamp")
                stamp = when.strftime("%Y-%m-%d") if hasattr(when, "strftime") else "unknown date"
                print(f"                   {item['address']}  {stamp}")
            if deployer.partial:
                print("                   (list truncated — see the explorer for the full history)")
        else:
            print("  Past projects  none found on this chain")
        print()

    print("  Research links")
    print(f"  {'-' * 62}")
    for name, url in report.links.items():
        print(f"  {name:<15} {url}")

    if report.errors:
        print()
        print("  Incomplete data")
        print(f"  {'-' * 62}")
        for error in report.errors:
            print(f"  - {error}")

    print()
    print("  This reports what the contract CAN do and who can do it. It cannot tell")
    print("  you intent, and it is not financial advice. Verify anything that matters")
    print("  against the source yourself.")
    print()


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width) or [""]


class _SyntheticSource:
    """Feeds the paper engine generated candles, for offline smoke tests."""

    def __init__(self, config: Config, seed: int = 7) -> None:
        self._candles = {
            symbol: generate_synthetic(bars=3000, timeframe=config.timeframe, seed=seed + i)
            for i, symbol in enumerate(config.symbols)
        }
        self._cursor = {symbol: 300 for symbol in config.symbols}

    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        series = self._candles[symbol]
        end = min(self._cursor[symbol], len(series))
        self._cursor[symbol] = min(end + 1, len(series))
        return series[max(0, end - limit) : end]

    def close(self) -> None:
        pass


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradingbot",
        description="Automated crypto trading bot with backtesting, paper trading and risk controls.",
    )
    parser.add_argument("--version", action="version", version=f"tradingbot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, *, data=False):
        p.add_argument("-c", "--config", help="path to a YAML config file")
        p.add_argument("-s", "--symbol", help="override the configured symbol")
        p.add_argument("-t", "--timeframe", help="override the configured timeframe")
        p.add_argument("--strategy", choices=available_strategies(), help="override the strategy")
        p.add_argument("--param", action="append", metavar="KEY=VALUE",
                       help="override a strategy parameter (repeatable)")
        p.add_argument("--log-level", default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"])
        if data:
            p.add_argument("--csv", help="load candles from this CSV instead of the cache")
            p.add_argument("--download", action="store_true",
                           help="download history from the exchange if not cached")
            p.add_argument("--days", type=int, default=365, help="days of history to download")
            p.add_argument("--synthetic", action="store_true",
                           help="use generated data (offline demo only; never for strategy selection)")
            p.add_argument("--bars", type=int, default=3000, help="synthetic bar count")
            p.add_argument("--seed", type=int, default=7, help="synthetic data seed")
            p.add_argument("--cash", type=float, help="override starting cash")

    p = sub.add_parser("backtest", help="replay a strategy over historical data")
    common(p, data=True)
    p.add_argument("--json", help="write full results to this JSON file")
    p.add_argument("--equity-csv", help="write the equity curve to this CSV file")
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("optimize", help="grid-search strategy parameters")
    common(p, data=True)
    p.add_argument("--grid", action="append", default=[], metavar="KEY=V1,V2",
                   help="parameter values to sweep (repeatable)")
    p.add_argument("--sort", default="sharpe",
                   choices=["sharpe", "return", "calmar", "profit_factor"])
    p.add_argument("--top", type=int, default=15, help="rows to display")
    p.set_defaults(func=cmd_optimize)

    p = sub.add_parser("paper", help="run the live loop with simulated money")
    common(p)
    p.add_argument("--synthetic", action="store_true", help="use generated data (offline demo)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--cash", type=float, help="override starting cash")
    p.add_argument("--iterations", type=int, help="stop after N cycles (default: run forever)")
    p.add_argument("--poll-interval", type=int, help="seconds between cycles (default: from config)")
    p.set_defaults(func=cmd_paper)

    p = sub.add_parser("live", help="run the live loop with REAL money")
    common(p)
    p.add_argument("--i-understand-the-risk", action="store_true",
                   help="required acknowledgement that live trading risks real funds")
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation prompt")
    p.add_argument("--iterations", type=int, help="stop after N cycles")
    p.add_argument("--poll-interval", type=int, help="seconds between cycles (default: from config)")
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("fetch", help="download and cache OHLCV history")
    common(p)
    p.add_argument("--days", type=int, default=365, help="days of history to download")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("serve", help="run the CBot web dashboard")
    common(p)
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address (default: localhost only)")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("research", help="review a token contract address")
    p.add_argument("address", help="contract address (0x...)")
    p.add_argument("--chain", default="ethereum",
                   help="chain to look on (ethereum, bsc, base, polygon, arbitrum, optimism, avalanche)")
    p.add_argument("--json", help="write the full report to this JSON file")
    p.add_argument("--print-report", action="store_true",
                   help="also print the report when writing JSON")
    p.add_argument("--max-deployments", type=int, default=25,
                   help="how many of the deployer's other contracts to list")
    p.add_argument("--log-level", default="WARNING",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.set_defaults(func=cmd_research, config=None)

    p = sub.add_parser("strategies", help="list strategies and their parameters")
    p.add_argument("--log-level", default="WARNING")
    p.set_defaults(func=cmd_strategies, config=None)

    p = sub.add_parser("status", help="show saved bot state")
    p.add_argument("-c", "--config", help="path to a YAML config file")
    p.add_argument("--log-level", default="WARNING")
    p.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(getattr(args, "log_level", "INFO"))
    try:
        return args.func(args) or 0
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
