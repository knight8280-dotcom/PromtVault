"""The dashboard's API handlers, kept separate from HTTP plumbing.

Each function takes a parsed request body and the server's base config, and
returns a JSON-ready dict. Long-running work returns a job id instead of a
result; the page polls for it.

Nothing here can place an order. That is a deliberate boundary, not an oversight:
live trading lives on the CLI behind its confirmation locks, and a browser tab is
not somewhere a real order should be one click away.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path

from ..backtest import Backtester
from ..config import Config, ConfigError, from_dict
from ..data import csv_store, generate_synthetic, load_history
from ..execution import FEE_TIERS, ExecutionModel, compare_execution, get_tier
from ..regime import RegimeDetector, RegimeGatedStrategy, regime_summary
from ..state import load_state, state_path
from ..strategies import available_strategies, get_strategy, strategy_class
from .jobs import JobContext

log = logging.getLogger(__name__)

MAX_BACKTEST_BARS = 20_000
MAX_GRID_COMBINATIONS = 240


class ApiError(Exception):
    """A request the client got wrong; reported as 4xx rather than a traceback."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


# ======================================================================
# Reference data
# ======================================================================
def describe_strategies() -> dict:
    out = []
    for name in available_strategies():
        if name.startswith("_"):  # test-only strategies never reach the UI
            continue
        cls = strategy_class(name)
        doc = (cls.__doc__ or "").strip().splitlines()
        out.append(
            {
                "name": name,
                "description": doc[0] if doc else "",
                "params": [
                    {"name": key, "default": value}
                    for key, value in sorted(cls.default_params.items())
                ],
            }
        )
    return {"strategies": out}


def describe_config(config: Config) -> dict:
    model = config.execution.execution_model()
    return {
        "symbols": config.symbols,
        "timeframe": config.timeframe,
        "strategy": config.strategy.name,
        "exchange": config.exchange.name,
        "testnet": config.exchange.testnet,
        "mode": config.execution.mode,
        "starting_cash": config.execution.starting_cash,
        "fee_rate": config.execution.fee_rate,
        "slippage_pct": config.execution.slippage_pct,
        "fee_tier": config.execution.fee_tier,
        "prefer_maker": config.execution.prefer_maker,
        "execution_summary": model.describe() if model else None,
        "risk": asdict(config.risk),
        "data_dir": config.data_dir,
    }


def describe_status(config: Config) -> dict:
    saved = load_state(state_path(config.state_dir))
    if not saved:
        return {"running": False, "positions": [], "message": "no saved state"}
    return {
        "running": True,
        "updated_at": saved.get("updated_at"),
        "cash": saved.get("cash", 0.0),
        "peak_equity": saved.get("peak_equity", 0.0),
        "realized_today": saved.get("realized_today", 0.0),
        "halted_reason": saved.get("halted_reason"),
        "positions": [
            {
                "symbol": symbol,
                "side": p.side.value,
                "amount": p.amount,
                "entry_price": p.entry_price,
                "stop_price": p.stop_price,
                "take_profit_price": p.take_profit_price,
                "opened_at": p.opened_at.isoformat(),
            }
            for symbol, p in saved.get("positions", {}).items()
        ],
    }


#: Dataset summaries keyed by (path, mtime, size). Every page asks for the
#: dataset list on mount, and a year of minute bars is half a million rows, so
#: parsing each CSV on every page load made the site feel slow for no reason.
#: A changed file changes its key, so `fetch` writing new bars is picked up.
_dataset_cache: dict[tuple, dict] = {}
_dataset_lock = threading.Lock()


def _describe_dataset(path: Path) -> dict | None:
    symbol, _, timeframe = path.stem.rpartition("_")
    if not symbol:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)

    with _dataset_lock:
        cached = _dataset_cache.get(key)
    if cached is not None:
        return cached

    try:
        candles = csv_store.load(path)
    except (ValueError, OSError) as exc:
        log.debug("skipping unreadable dataset %s: %s", path, exc)
        return None
    if not candles:
        return None
    summary = {
        "symbol": symbol.replace("-", "/"),
        "timeframe": timeframe,
        "bars": len(candles),
        "start": candles[0].timestamp.isoformat(),
        "end": candles[-1].timestamp.isoformat(),
        "last_price": candles[-1].close,
    }
    with _dataset_lock:
        # Drop stale entries for the same file so a rewritten CSV does not
        # leave its old summary behind forever.
        for old in [k for k in _dataset_cache if k[0] == key[0]]:
            del _dataset_cache[old]
        _dataset_cache[key] = summary
    return summary


def describe_datasets(config: Config) -> dict:
    """What market data is cached locally, so the UI can offer it."""
    data_dir = Path(config.data_dir)
    if not data_dir.exists():
        return {"datasets": []}

    out = []
    for path in sorted(data_dir.glob("*.csv")):
        summary = _describe_dataset(path)
        if summary is not None:
            out.append(summary)
    return {"datasets": out}


def describe_request(kind: str, body: dict, base: Config) -> str:
    """A one-line label for a queued job, so a listing says what it was."""
    if kind == "carry":
        venue = str(body.get("venue") or "binance")
        symbols = body.get("symbols")
        scope = f"{len(symbols)} symbols" if isinstance(symbols, list) and symbols else (
            f"top {int(body.get('limit') or 20)}"
        )
        return f"{venue} · {scope}"

    strategy = str(body.get("strategy") or base.strategy.name)
    if body.get("synthetic"):
        data = f"synthetic {int(body.get('bars') or 3000)} bars"
    else:
        data = f"{body.get('symbol') or base.symbols[0]} {body.get('timeframe') or base.timeframe}"
    return f"{strategy} · {data}"


def describe_execution(body: dict) -> dict:
    """Fee tiers and what each mode costs, for the execution page."""
    tier_name = body.get("tier")
    tiers = [get_tier(tier_name)] if tier_name else list(FEE_TIERS.values())
    return {
        "tiers": [
            {
                "name": tier.name,
                "key": key,
                "maker": tier.maker,
                "taker": tier.taker,
                "rows": compare_execution(tier),
            }
            for key, tier in FEE_TIERS.items()
            if not tier_name or tier is tiers[0]
        ]
    }


# ======================================================================
# Shared helpers
# ======================================================================
def build_config(base: Config, body: dict) -> Config:
    """Overlay a request's settings onto the server's config."""
    risk = {**asdict(base.risk), **(body.get("risk") or {})}
    execution = {
        "starting_cash": float(body.get("starting_cash") or base.execution.starting_cash),
        "fee_rate": float(body.get("fee_rate", base.execution.fee_rate)),
        "slippage_pct": float(body.get("slippage_pct", base.execution.slippage_pct)),
        "min_order_notional": base.execution.min_order_notional,
    }
    if body.get("fee_tier"):
        execution["fee_tier"] = body["fee_tier"]
        execution["prefer_maker"] = bool(body.get("prefer_maker", False))
        execution["maker_fill_rate"] = float(body.get("maker_fill_rate", 0.8))

    try:
        return from_dict(
            {
                "symbols": [str(body.get("symbol") or base.symbols[0])],
                "timeframe": str(body.get("timeframe") or base.timeframe),
                "execution": execution,
                "risk": risk,
                "data_dir": base.data_dir,
                "state_dir": base.state_dir,
            }
        )
    except ConfigError as exc:
        raise ApiError(str(exc)) from exc


def build_strategy(body: dict, config: Config):
    name = str(body.get("strategy") or config.strategy.name)
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise ApiError("params must be an object")

    try:
        strategy = get_strategy(name, **params)
    except KeyError as exc:
        raise ApiError(exc.args[0]) from exc
    except ValueError as exc:
        raise ApiError(str(exc)) from exc

    if body.get("regime_gate"):
        allow = str(body.get("regime_allow") or "trend")
        try:
            strategy = RegimeGatedStrategy(strategy, RegimeDetector(), allow=allow)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
    return strategy


def load_candles(body: dict, config: Config, symbol: str):
    if body.get("synthetic"):
        bars = int(body.get("bars") or 3000)
        if not 100 <= bars <= MAX_BACKTEST_BARS:
            raise ApiError(f"bars must be between 100 and {MAX_BACKTEST_BARS}")
        return generate_synthetic(
            bars=bars, timeframe=config.timeframe, seed=int(body.get("seed") or 7)
        )
    try:
        # Reads the cache only; `fetch` is what downloads.
        return load_history(symbol, config.timeframe, data_dir=config.data_dir)
    except FileNotFoundError as exc:
        raise ApiError(
            f"no cached data for {symbol} {config.timeframe}. Fetch it first, or "
            f"tick 'synthetic data'."
        ) from exc


def serialise_trades(trades) -> list[dict]:
    return [
        {
            "opened_at": t.opened_at.isoformat(),
            "closed_at": t.closed_at.isoformat(),
            "side": t.side.value,
            "amount": t.amount,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "net_pnl": t.net_pnl,
            "return_pct": t.return_pct * 100,
            "reason": t.reason,
        }
        for t in trades
    ]


def _thin(points, limit: int = 1500):
    """Downsample a curve for transport; a chart cannot draw 20k points anyway."""
    if len(points) <= limit:
        return points
    step = len(points) / limit
    return [points[int(i * step)] for i in range(limit)]


# ======================================================================
# Backtest
# ======================================================================
def run_backtest(base: Config, body: dict) -> dict:
    config = build_config(base, body)
    symbol = config.symbols[0]
    strategy = build_strategy(body, config)
    candles = load_candles(body, config, symbol)

    try:
        result = Backtester(config, strategy).run(symbol, candles)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc

    blocked = getattr(strategy, "blocked_entries", {})
    return {
        "symbol": symbol,
        "timeframe": config.timeframe,
        "strategy": result.strategy,
        "synthetic": bool(body.get("synthetic")),
        "metrics": result.metrics.as_dict(),
        "halted_reason": result.halted_reason,
        "rejections": result.rejections,
        "regime_blocked": blocked,
        "equity_curve": [
            {"t": p.timestamp.isoformat(), "equity": round(p.equity, 2)}
            for p in _thin(result.equity_curve)
        ],
        "benchmark_curve": [
            {"t": p.timestamp.isoformat(), "equity": round(p.equity, 2)}
            for p in _thin(result.benchmark_curve)
        ],
        "trades": serialise_trades(result.trades),
    }


# ======================================================================
# Validate (background job)
# ======================================================================
def run_validate(base: Config, body: dict, ctx: JobContext) -> dict:
    from ..validation import (
        average_holding_bars,
        bootstrap_returns,
        cost_sensitivity,
        random_entry_baseline,
    )

    config = build_config(base, body)
    symbol = config.symbols[0]
    strategy = build_strategy(body, config)
    candles = load_candles(body, config, symbol)

    ctx.progress(0.1, "running the backtest")
    try:
        result = Backtester(config, strategy).run(symbol, candles)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc

    m = result.metrics
    checks = []
    excess = m.excess_return_pct or 0.0
    checks.append(
        {
            "id": "benchmark", "name": "beats buy and hold", "passed": excess > 0,
            "detail": f"{m.total_return_pct:.2f}% versus {m.benchmark_return_pct:.2f}% holding",
            "value": excess,
        }
    )

    ctx.progress(0.35, "resampling the trade sequence")
    boot = bootstrap_returns(result.trades, config.execution.starting_cash)
    if boot is None:
        checks.append({"id": "bootstrap", "name": "statistically positive", "passed": False,
                       "detail": "no trades to resample", "value": None})
        bootstrap_payload = None
    else:
        solid = not boot.interval_includes_zero and boot.low_return_pct > 0
        checks.append(
            {
                "id": "bootstrap", "name": "statistically positive", "passed": solid,
                "detail": (
                    f"90% interval [{boot.low_return_pct:.2f}%, {boot.high_return_pct:.2f}%], "
                    f"{boot.probability_profitable:.0%} chance of profit"
                ),
                "value": boot.low_return_pct,
            }
        )
        bootstrap_payload = {
            "low": boot.low_return_pct, "median": boot.median_return_pct,
            "high": boot.high_return_pct, "probability_profitable": boot.probability_profitable,
            "observed": boot.observed_return_pct, "trades": boot.trade_count,
            "spans_zero": boot.interval_includes_zero,
        }

    ctx.progress(0.6, "comparing against random entries")
    holding = average_holding_bars(result.trades, config.timeframe)
    baseline = random_entry_baseline(
        candles, m.total_trades, holding, strategy_return_pct=m.total_return_pct,
        fee_rate=config.execution.fee_rate, slippage_pct=config.execution.slippage_pct,
    )
    if baseline is None:
        checks.append({"id": "random", "name": "beats random entries", "passed": False,
                       "detail": "not enough trades to compare", "value": None})
        baseline_payload = None
    else:
        checks.append(
            {
                "id": "random", "name": "beats random entries", "passed": baseline.significant,
                "detail": (
                    f"beat {baseline.percentile:.0%} of random traders "
                    f"(p = {baseline.p_value:.3f})"
                ),
                "value": baseline.percentile,
            }
        )
        baseline_payload = {
            "strategy": baseline.strategy_return_pct,
            "random_median": baseline.median_random_return_pct,
            "percentile": baseline.percentile, "p_value": baseline.p_value,
            "iterations": baseline.iterations, "holding_bars": baseline.holding_bars,
        }

    ctx.progress(0.8, "sweeping trading costs")
    costs = cost_sensitivity(config, strategy, candles, symbol=symbol)
    breakeven = costs.breakeven_fee
    survives = breakeven is not None and breakeven > config.execution.fee_rate
    checks.append(
        {
            "id": "costs", "name": "survives realistic fees", "passed": survives,
            "detail": (
                f"breaks even around {breakeven:.4f}, you pay {config.execution.fee_rate:.4f}"
                if breakeven is not None and breakeven > 0
                else "unprofitable at any fee level tested"
            ),
            "value": breakeven,
        }
    )

    ctx.progress(1.0, "done")
    return {
        "symbol": symbol,
        "strategy": result.strategy,
        "metrics": m.as_dict(),
        "checks": checks,
        "passed": sum(1 for c in checks if c["passed"]),
        "total": len(checks),
        "bootstrap": bootstrap_payload,
        "random_baseline": baseline_payload,
        "cost_curve": [
            {"fee_rate": p.fee_rate, "total_return_pct": p.total_return_pct, "trades": p.trades}
            for p in costs.points
        ],
        "fee_rate": config.execution.fee_rate,
    }


# ======================================================================
# Walk-forward (background job)
# ======================================================================
def run_walkforward(base: Config, body: dict, ctx: JobContext) -> dict:
    from ..validation import walk_forward

    config = build_config(base, body)
    symbol = config.symbols[0]
    name = str(body.get("strategy") or config.strategy.name)

    grid = body.get("grid") or {}
    if not isinstance(grid, dict) or not grid:
        raise ApiError("a parameter grid is required, e.g. {\"fast_period\": [10, 20]}")

    combinations = 1
    for values in grid.values():
        if not isinstance(values, list) or not values:
            raise ApiError("each grid entry must be a non-empty list of values")
        combinations *= len(values)
    if combinations > MAX_GRID_COMBINATIONS:
        raise ApiError(
            f"{combinations} parameter combinations is too many for one run "
            f"(limit {MAX_GRID_COMBINATIONS}). Narrow the grid."
        )

    candles = load_candles(body, config, symbol)
    ctx.progress(0.05, f"{combinations} combinations per window")

    try:
        result = walk_forward(
            config, name, grid, candles,
            train_bars=int(body.get("train_bars") or 1000),
            test_bars=int(body.get("test_bars") or 250),
            scorer=str(body.get("scorer") or "sharpe"),
            symbol=symbol,
        )
    except ValueError as exc:
        raise ApiError(str(exc)) from exc

    ctx.progress(0.95, "summarising")
    if not result.windows:
        raise ApiError("no complete train/test windows fitted in this data")

    return {
        "symbol": symbol,
        "strategy": name,
        "scorer": result.scorer,
        "windows": [
            {
                "index": w.index, "params": w.params,
                "in_sample": w.in_sample.total_return_pct,
                "out_of_sample": w.out_of_sample.total_return_pct,
                "start_equity": w.start_equity, "end_equity": w.end_equity,
            }
            for w in result.windows
        ],
        "in_sample_mean": result.in_sample_mean,
        "out_of_sample_mean": result.out_of_sample_mean,
        "degradation": result.degradation,
        "profitable_windows": result.profitable_windows,
        "total_windows": len(result.windows),
        "parameter_stability": result.parameter_stability,
        "combined": result.combined.as_dict() if result.combined else None,
        "equity_curve": [
            {"t": p.timestamp.isoformat(), "equity": round(p.equity, 2)}
            for p in _thin(result.equity_curve)
        ],
        "trades": serialise_trades(result.trades),
    }


# ======================================================================
# Regime
# ======================================================================
def run_regime(base: Config, body: dict) -> dict:
    config = build_config(base, body)
    symbol = config.symbols[0]
    candles = load_candles(body, config, symbol)

    detector = RegimeDetector(period=int(body.get("period") or 30))
    if len(candles) < detector.period + 1:
        raise ApiError(f"need more than {detector.period} bars to read a regime")

    current = detector.detect(candles)
    summary = regime_summary(candles, detector)

    # A sampled timeline, so the page can show how the regime moved.
    step = max(1, len(candles) // 300)
    timeline = []
    for i in range(detector.period + 1, len(candles), step):
        reading = detector.detect(candles[: i + 1])
        timeline.append(
            {
                "t": candles[i].timestamp.isoformat(),
                "regime": reading.regime.value,
                "efficiency": reading.efficiency,
                "price": candles[i].close,
            }
        )

    return {
        "symbol": symbol,
        "timeframe": config.timeframe,
        "bars": len(candles),
        "current": {
            "regime": current.regime.value,
            "efficiency": current.efficiency,
            "volatility": current.volatility,
            "reason": current.reason,
        },
        "summary": summary,
        "timeline": timeline,
    }


# ======================================================================
# Carry (background job — one network call per symbol)
# ======================================================================
def run_carry(body: dict, ctx: JobContext) -> dict:
    from ..carry import CarryCosts, CarryScanner, FundingSourceError

    venue = str(body.get("venue") or "binance")
    spot_tier = get_tier(str(body.get("spot_tier") or "binance"))
    perp_tier = get_tier(str(body.get("perp_tier") or "binance_perp"))
    maker = bool(body.get("maker", True))
    fill_rate = float(body.get("fill_rate") or 0.8)

    costs = CarryCosts(
        spot_fee=ExecutionModel(spot_tier, prefer_maker=maker, maker_fill_rate=fill_rate).effective_fee(),
        perp_fee=ExecutionModel(perp_tier, prefer_maker=maker, maker_fill_rate=fill_rate).effective_fee(),
        slippage_pct=float(body.get("slippage_pct") or 0.0001),
        borrow_apr=float(body.get("borrow_apr") or 0.0),
    )

    ctx.progress(0.05, f"connecting to {venue}")
    try:
        from ..carry import CcxtFundingSource

        source = CcxtFundingSource(venue)
    except FundingSourceError as exc:
        raise ApiError(str(exc), HTTPStatus.SERVICE_UNAVAILABLE) from exc

    try:
        symbols = body.get("symbols")
        if not symbols:
            ctx.progress(0.1, "listing perpetual markets")
            symbols = source.perpetual_symbols()[: int(body.get("limit") or 20)]

        scanner = CarryScanner(
            source, costs,
            history_limit=int(body.get("history") or 30),
            max_breakeven_hours=float(body.get("max_breakeven_days") or 5) * 24,
        )

        # Scan one symbol at a time so progress is real rather than a spinner.
        from ..carry.scanner import ScanResult

        result = ScanResult()
        for i, symbol in enumerate(symbols):
            ctx.progress(0.1 + 0.85 * (i / max(1, len(symbols))), f"scanning {symbol}")
            partial = scanner.scan([symbol])
            result.opportunities.extend(partial.opportunities)
            result.errors.extend(partial.errors)
            result.scanned += partial.scanned
    finally:
        source.close()

    ctx.progress(1.0, "done")
    payload = result.as_dict()
    payload["costs"] = {
        "spot_fee": costs.spot_fee, "perp_fee": costs.perp_fee,
        "slippage_pct": costs.slippage_pct, "round_trip": costs.round_trip_cost,
        "maker": maker, "venue": venue,
    }
    return payload
