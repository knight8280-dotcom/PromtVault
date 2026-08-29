"""Command line interface.

Subcommands:
  backtest  replay a strategy over historical data
  paper     run the live loop against real prices with simulated money
  live      run the live loop with real money (guarded, see `_confirm_live`)
  preflight validate a live-trading setup without placing orders
  fetch     download and cache OHLCV history
  serve     run the CBot web dashboard
  research  review a token contract address before you trade it
  carry     scan perpetual funding for market-neutral carry
  execution what your fees cost, and the edge needed to beat them
  regime    which market regimes an instrument spends its time in
  optimize  grid-search strategy parameters over historical data
  validate  stress-test a result: benchmark, luck, random baseline, costs
  walkforward  optimise on one window and test on the next unseen one
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
    if args.source == "coingecko":
        return _fetch_public(config, args)

    from .data.feed import download

    for symbol in config.symbols:
        candles = download(
            symbol, config.timeframe, config.exchange, days=args.days, data_dir=config.data_dir
        )
        path = csv_store.cache_path(config.data_dir, symbol, config.timeframe)
        span = f"{candles[0].timestamp:%Y-%m-%d} to {candles[-1].timestamp:%Y-%m-%d}" if candles else "empty"
        print(f"  {symbol} {config.timeframe}: {len(candles)} candles ({span}) -> {path}")
    return 0


def _fetch_public(config: Config, args) -> int:
    """Fetch from CoinGecko: no API key, works where exchanges are geo-blocked."""
    from .data import coingecko, csv_store

    for symbol in config.symbols:
        try:
            if config.timeframe == "1d":
                candles = coingecko.fetch_daily(symbol, days=args.days)
            else:
                candles = coingecko.fetch_hourly(symbol, days=min(args.days, 90))
        except coingecko.CoinGeckoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        path = csv_store.cache_path(config.data_dir, symbol, config.timeframe)
        csv_store.save(path, candles)
        span = f"{candles[0].timestamp:%Y-%m-%d} to {candles[-1].timestamp:%Y-%m-%d}"
        print(f"  {symbol} {config.timeframe}: {len(candles)} candles ({span}) -> {path}")

    if config.timeframe != "1d":
        print()
        print("  Note: this source returns closing prices only, so bars have no true")
        print("  intrabar high or low. Stops and targets are evaluated against the close")
        print("  and will trigger less often than in live trading. Confirm anything")
        print("  promising on exchange data before trusting it.")
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


STATUS_MARKS = {"pass": "OK  ", "warn": "WARN", "fail": "FAIL", "skip": "--  "}


def cmd_preflight(args) -> int:
    """Check a live-trading setup without placing a single order."""
    config = _resolve_config(args)
    from .preflight import run_preflight

    report = run_preflight(config)

    print()
    print(f"  Pre-flight: {config.exchange.name} "
          f"({'testnet' if config.exchange.testnet else 'PRODUCTION'})")
    print(f"  {'=' * 66}")
    for check in report.checks:
        print(f"  [{STATUS_MARKS.get(check.status.value, '?')}] {check.name}")
        print(f"         {check.message}")
        if check.fix:
            for line in _wrap(check.fix, 62):
                print(f"         -> {line}")
        print()

    if report.failures:
        print(f"  NOT READY — {len(report.failures)} check(s) failed. Fix them before going live.")
        print()
        return 1

    if report.warnings:
        print(f"  Ready, with {len(report.warnings)} warning(s) above. Read them before starting.")
    else:
        print("  Ready. Start small: your first live run should risk an amount you would")
        print("  not mind losing entirely.")
    print()
    return 0


def cmd_validate(args) -> int:
    """Attack a backtest result: benchmark, resampling, random baseline, costs."""
    config = _resolve_config(args)
    strategy = _resolve_strategy(args, config)
    symbol = config.symbols[0]

    try:
        candles = _get_candles(args, config, symbol)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    from .validation import (
        average_holding_bars, bootstrap_returns, cost_sensitivity, random_entry_baseline,
    )

    try:
        result = Backtester(config, strategy).run(symbol, candles)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    m = result.metrics
    print()
    print(f"  Validating {strategy.describe()}")
    print(f"  on {symbol} {config.timeframe}, {len(candles)} bars")
    print(f"  {'=' * 68}")

    checks = []

    # 1 — against doing nothing at all.
    print()
    print("  1. Against buy and hold")
    print(f"     strategy      {m.total_return_pct:>8.2f}%   (max drawdown {m.max_drawdown_pct:.2f}%)")
    print(f"     buy and hold  {m.benchmark_return_pct:>8.2f}%   (max drawdown {m.benchmark_max_drawdown_pct:.2f}%)")
    excess = m.excess_return_pct or 0.0
    beat = excess > 0
    checks.append(("beats buy and hold", beat))
    print(f"     excess        {excess:>8.2f}%   -> {'BEATS holding' if beat else 'LOSES to holding'}")
    if not beat:
        print("     A strategy that underperforms holding has cost you money to run.")

    # 2 — how much of this was ordering luck.
    print()
    print("  2. Is the result distinguishable from luck?")
    boot = bootstrap_returns(result.trades, config.execution.starting_cash)
    if boot is None:
        print("     no trades to resample")
        checks.append(("statistically positive", False))
    else:
        print(f"     {boot.trade_count} trades resampled {boot.samples:,} times")
        print(f"     90% confidence interval  [{boot.low_return_pct:+.2f}%, {boot.high_return_pct:+.2f}%]")
        print(f"     probability of profit    {boot.probability_profitable:.1%}")
        solid = not boot.interval_includes_zero and boot.low_return_pct > 0
        checks.append(("statistically positive", solid))
        if boot.interval_includes_zero:
            print("     -> The interval spans zero: this is not distinguishable from break-even.")
        else:
            print(f"     -> Interval excludes zero.")

    # 3 — versus a trader with no idea what they are doing.
    print()
    print("  3. Against random entries, trading just as often")
    holding = average_holding_bars(result.trades, config.timeframe)
    baseline = random_entry_baseline(
        candles, m.total_trades, holding, strategy_return_pct=m.total_return_pct,
        fee_rate=config.execution.fee_rate, slippage_pct=config.execution.slippage_pct,
    )
    if baseline is None:
        print("     not enough trades to compare")
        checks.append(("beats random entries", False))
    else:
        print(f"     {baseline.trade_count} random trades held {baseline.holding_bars} bars, "
              f"{baseline.iterations:,} runs")
        print(f"     strategy       {baseline.strategy_return_pct:>8.2f}%")
        print(f"     random median  {baseline.median_random_return_pct:>8.2f}%")
        print(f"     beat {baseline.percentile:.1%} of random traders (p = {baseline.p_value:.3f})")
        checks.append(("beats random entries", baseline.significant))
        if not baseline.significant:
            print("     -> Not significant. Random entries at this frequency do about as well,")
            print("        so the strategy logic is not what produced the result.")

    # 4 — does it survive real trading costs.
    print()
    print("  4. Sensitivity to trading costs")
    costs = cost_sensitivity(config, strategy, candles, symbol=symbol)
    for point in costs.points:
        marker = "  <- your setting" if abs(point.fee_rate - config.execution.fee_rate) < 1e-9 else ""
        print(f"     fee {point.fee_rate:.4f}   {point.total_return_pct:>8.2f}%{marker}")
    breakeven = costs.breakeven_fee
    survives = breakeven is not None and breakeven > config.execution.fee_rate
    checks.append(("survives realistic fees", survives))
    if breakeven is None:
        print("     -> Unprofitable at every fee level tested, including zero.")
    elif breakeven <= 0:
        print("     -> Only profitable at zero fees. Not tradable.")
    else:
        print(f"     -> Breaks even around {breakeven:.4f}; you pay {config.execution.fee_rate:.4f}.")

    # Verdict
    passed = sum(1 for _, ok in checks if ok)
    print()
    print(f"  {'=' * 68}")
    print(f"  Verdict: {passed} of {len(checks)} checks passed")
    for name, ok in checks:
        print(f"     [{'PASS' if ok else 'FAIL'}] {name}")
    print()
    if passed == len(checks):
        print("  Every check passed on this data. That is necessary, not sufficient:")
        print("  run walkforward next to see whether it survives out of sample.")
    elif passed == 0:
        print("  This strategy does not work on this data. That is the normal result,")
        print("  and finding it here costs nothing.")
    else:
        print("  Mixed. Treat the failed checks as disqualifying until you can explain")
        print("  them — a strategy that fails any one of these is not ready for money.")
    print()
    return 0


def cmd_walkforward(args) -> int:
    """Optimise on one window, test on the next unseen one, roll forward."""
    config = _resolve_config(args)
    symbol = config.symbols[0]
    name = getattr(args, "strategy", None) or config.strategy.name

    grid = {}
    for pair in args.grid:
        key, _, raw = pair.partition("=")
        grid[key.strip()] = [_coerce(v.strip()) for v in raw.split(",")]
    if not grid:
        raise SystemExit("error: --grid is required, e.g. --grid fast_period=10,20")

    try:
        candles = _get_candles(args, config, symbol)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    from .validation import walk_forward

    try:
        wf = walk_forward(
            config, name, grid, candles,
            train_bars=args.train, test_bars=args.test, scorer=args.sort, symbol=symbol,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not wf.windows:
        print("error: no complete train/test windows fitted in this data", file=sys.stderr)
        return 1

    print()
    print(f"  Walk-forward: {name} on {symbol} {config.timeframe}")
    print(f"  {args.train} train / {args.test} test bars, optimised for {args.sort}")
    print(f"  {'=' * 72}")
    print(f"  {'win':<5}{'parameters':<34}{'in-sample':>12}{'out-of-sample':>16}")
    print(f"  {'-' * 72}")
    for w in wf.windows:
        label = ", ".join(f"{k}={v}" for k, v in sorted(w.params.items()))
        print(f"  {w.index:<5}{label[:33]:<34}{w.in_sample.total_return_pct:>11.2f}%"
              f"{w.out_of_sample.total_return_pct:>15.2f}%")

    print()
    print(f"  In-sample mean        {wf.in_sample_mean:>8.2f}%")
    print(f"  Out-of-sample mean    {wf.out_of_sample_mean:>8.2f}%")
    print(f"  Degradation           {wf.degradation:>8.2f}    (1.0 = held up, <=0 = fitted noise)")
    print(f"  Profitable windows    {wf.profitable_windows:>8} of {len(wf.windows)}")
    if wf.combined:
        print(f"  Combined out-of-sample{wf.combined.total_return_pct:>8.2f}%   "
              f"(max drawdown {wf.combined.max_drawdown_pct:.2f}%)")
        if wf.combined.benchmark_return_pct is not None:
            print(f"  Buy and hold, same span{wf.combined.benchmark_return_pct:>7.2f}%")

    print()
    print("  Parameter stability (distinct values chosen across windows)")
    for key, count in wf.parameter_stability.items():
        note = "stable" if count == 1 else ("drifting" if count <= 2 else "unstable — fitting noise")
        print(f"     {key:<24}{count:>3}   {note}")

    print()
    honest = wf.combined.total_return_pct if wf.combined else 0.0
    hold = wf.combined.benchmark_return_pct if wf.combined and wf.combined.benchmark_return_pct is not None else None
    if honest <= 0:
        print("  Out of sample this loses money. The in-sample numbers were the optimiser")
        print("  fitting noise — which is what a grid search does by default.")
    elif hold is not None and honest < hold:
        print("  Profitable out of sample, but buy and hold did better over the same span")
        print("  with no execution risk. That is not an edge worth running.")
    else:
        print("  Survives out of sample. Test other periods and instruments before")
        print("  trusting it, and re-check the cost sensitivity at your real fee tier.")
    print()
    return 0


def cmd_carry(args) -> int:
    """Scan perpetual funding for carry that survives its own costs."""
    config = _resolve_config(args)
    from .carry import CarryCosts, CarryScanner, FundingSourceError, format_scan
    from .execution import ExecutionModel, get_tier

    spot = get_tier(args.spot_tier)
    perp = get_tier(args.perp_tier)
    spot_model = ExecutionModel(spot, prefer_maker=args.maker, maker_fill_rate=args.fill_rate)
    perp_model = ExecutionModel(perp, prefer_maker=args.maker, maker_fill_rate=args.fill_rate)
    costs = CarryCosts(
        spot_fee=spot_model.effective_fee(),
        perp_fee=perp_model.effective_fee(),
        slippage_pct=max(spot_model.effective_slippage(), perp_model.effective_slippage()),
        borrow_apr=args.borrow_apr,
    )

    try:
        from .carry import CcxtFundingSource

        source = CcxtFundingSource(args.venue)
    except FundingSourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        scanner = CarryScanner(source, costs, history_limit=args.history,
                               max_breakeven_hours=args.max_breakeven_days * 24)
        result = scanner.scan(args.symbols) if args.symbols else scanner.scan_all(limit=args.limit)
    finally:
        source.close()

    print(format_scan(result, costs))
    if args.json:
        Path(args.json).write_text(json.dumps(result.as_dict(), indent=2, default=str))
        print(f"  Wrote {args.json}\n")
    return 0 if result.opportunities else 1


def cmd_execution(args) -> int:
    """Show what execution actually costs, and the edge needed to overcome it."""
    from .execution import FEE_TIERS, compare_execution, get_tier

    if args.tier:
        tiers = [get_tier(args.tier)]
    else:
        tiers = [FEE_TIERS[name] for name in sorted(FEE_TIERS) if name != "zero"]

    print()
    print("  Execution cost, and the gross move a trade must capture to break even")
    print(f"  {'=' * 74}")
    for tier in tiers:
        print()
        print(f"  {tier.name}")
        print(f"    maker {tier.maker:.4%}   taker {tier.taker:.4%}")
        print(f"    {'mode':<10}{'fill rate':>11}{'eff. fee':>11}{'round trip':>13}{'breakeven move':>17}")
        for row in compare_execution(tier):
            label = row["mode"] if row["mode"] == "taker" else f"maker"
            print(f"    {label:<10}{row['fill_rate']:>10.0%}{row['effective_fee']:>11.4%}"
                  f"{row['round_trip']:>13.4%}{row['breakeven_pct']:>16.3f}%")
    print()
    print("  A strategy whose average winner is smaller than the breakeven move cannot")
    print("  be profitable, however often it is right. Check yours against this table.")
    print()
    return 0


def cmd_regime(args) -> int:
    """Report which regimes an instrument spends its time in."""
    config = _resolve_config(args)
    from .regime import RegimeDetector, regime_summary

    detector = RegimeDetector(period=args.period)
    for symbol in config.symbols:
        try:
            candles = _get_candles(args, config, symbol)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        summary = regime_summary(candles, detector)
        current = detector.detect(candles)

        print()
        print(f"  {symbol} {config.timeframe} — {len(candles)} bars")
        print(f"  {'=' * 62}")
        for name, share in sorted(summary.items(), key=lambda kv: -kv[1]):
            bar = "#" * int(share * 40)
            print(f"    {name:<12}{share:>6.0%}  {bar}")
        print()
        print(f"  Now: {current.regime.value} — {current.reason}")
        print()
        trending = summary.get("trending", 0) + summary.get("volatile", 0)
        print(f"  Trend strategies have a premise {trending:.0%} of the time;")
        print(f"  mean reversion has one {1 - trending:.0%} of the time. Running either")
        print("  outside its regime pays fees for nothing.")
        print()
    return 0


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

    p = sub.add_parser("carry", help="scan perpetual funding for market-neutral carry")
    p.add_argument("--venue", default="binance", help="perpetual venue to scan")
    p.add_argument("--symbols", nargs="*", help="specific perp symbols (default: scan the venue)")
    p.add_argument("--limit", type=int, default=25, help="how many perps to scan")
    p.add_argument("--history", type=int, default=30, help="funding intervals of history to weigh")
    p.add_argument("--spot-tier", default="binance", help="fee tier for the spot leg")
    p.add_argument("--perp-tier", default="binance_perp", help="fee tier for the perp leg")
    p.add_argument("--maker", action="store_true", help="assume maker execution on both legs")
    p.add_argument("--fill-rate", type=float, default=0.8, help="assumed maker fill rate")
    p.add_argument("--borrow-apr", type=float, default=0.0, help="cost of margin, as a fraction")
    p.add_argument("--max-breakeven-days", type=float, default=5.0,
                   help="reject carry that takes longer than this to cover its own fees")
    p.add_argument("--json", help="write the scan to this JSON file")
    p.add_argument("-c", "--config", help="path to a YAML config file")
    p.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.set_defaults(func=cmd_carry)

    p = sub.add_parser("execution", help="what your fees cost, and the edge needed to beat them")
    p.add_argument("--tier", help="a single fee tier to show")
    p.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.set_defaults(func=cmd_execution, config=None)

    p = sub.add_parser("regime", help="which market regimes an instrument spends its time in")
    common(p, data=True)
    p.add_argument("--period", type=int, default=30, help="bars in the efficiency window")
    p.set_defaults(func=cmd_regime)

    p = sub.add_parser("validate", help="stress-test a backtest result for luck and costs")
    common(p, data=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("walkforward", help="optimise and test on unseen data, rolling forward")
    common(p, data=True)
    p.add_argument("--grid", action="append", default=[], metavar="KEY=V1,V2",
                   help="parameter values to sweep (repeatable)")
    p.add_argument("--train", type=int, default=1000, help="bars in each training window")
    p.add_argument("--test", type=int, default=250, help="bars in each unseen test window")
    p.add_argument("--sort", default="sharpe", choices=["sharpe", "return", "calmar", "excess"],
                   help="what to optimise for on the training window")
    p.set_defaults(func=cmd_walkforward)

    p = sub.add_parser("preflight", help="check a live-trading setup before you use it")
    common(p)
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("fetch", help="download and cache OHLCV history")
    common(p)
    p.add_argument("--days", type=int, default=365, help="days of history to download")
    p.add_argument("--source", default="exchange", choices=["exchange", "coingecko"],
                   help="where to get data: the configured exchange (needs ccxt and a "
                        "reachable venue) or CoinGecko (no key, close prices only)")
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
