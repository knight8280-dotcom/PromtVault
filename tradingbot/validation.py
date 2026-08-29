"""Tools for deciding whether a backtest result means anything.

A single backtest number is nearly worthless on its own: it is one path, chosen
after the fact, usually on data the parameters were fitted to. Everything here
exists to attack a result rather than present it — out-of-sample testing,
resampling, a random-trader baseline, and cost sensitivity.

None of this manufactures an edge. It tells you whether you have one.
"""

from __future__ import annotations

import itertools
import logging
import random
from dataclasses import dataclass, field

from .backtest import Backtester
from .config import Config
from .metrics import Metrics, buy_and_hold, compute
from .models import Candle, EquityPoint, Trade
from .strategies import get_strategy
from .strategies.base import Strategy

log = logging.getLogger(__name__)

SCORERS = {
    "sharpe": lambda m: m.sharpe_ratio,
    "return": lambda m: m.total_return_pct,
    "calmar": lambda m: m.calmar_ratio,
    "excess": lambda m: (m.excess_return_pct if m.excess_return_pct is not None else m.total_return_pct),
}


# ======================================================================
# Walk-forward analysis
# ======================================================================
@dataclass
class Window:
    """One train/test fold, with the parameters chosen on the training half."""

    index: int
    train_start: int
    train_end: int
    test_end: int
    params: dict
    in_sample: Metrics
    out_of_sample: Metrics
    start_equity: float
    end_equity: float


@dataclass
class WalkForwardResult:
    windows: list[Window] = field(default_factory=list)
    combined: Metrics | None = None
    benchmark: Metrics | None = None
    equity_curve: list[EquityPoint] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    strategy: str = ""
    scorer: str = "sharpe"

    @property
    def in_sample_mean(self) -> float:
        if not self.windows:
            return 0.0
        return sum(w.in_sample.total_return_pct for w in self.windows) / len(self.windows)

    @property
    def out_of_sample_mean(self) -> float:
        if not self.windows:
            return 0.0
        return sum(w.out_of_sample.total_return_pct for w in self.windows) / len(self.windows)

    @property
    def degradation(self) -> float:
        """How much of the in-sample return survives out of sample, as a ratio.

        Near 1.0 means the edge held up. Near or below 0 means the optimiser was
        fitting noise, which is the usual outcome.
        """
        if self.in_sample_mean == 0:
            return 0.0
        return self.out_of_sample_mean / self.in_sample_mean

    @property
    def profitable_windows(self) -> int:
        return sum(1 for w in self.windows if w.out_of_sample.total_return_pct > 0)

    @property
    def parameter_stability(self) -> dict[str, int]:
        """How many distinct values the optimiser picked for each parameter.

        A parameter that changes every window is being fitted to noise.
        """
        counts: dict[str, set] = {}
        for window in self.windows:
            for key, value in window.params.items():
                counts.setdefault(key, set()).add(value)
        return {key: len(values) for key, values in sorted(counts.items())}


def walk_forward(
    config: Config,
    strategy_name: str,
    grid: dict[str, list],
    candles: list[Candle],
    *,
    train_bars: int = 1000,
    test_bars: int = 250,
    scorer: str = "sharpe",
    symbol: str = "BTC/USDT",
) -> WalkForwardResult:
    """Optimise on a window, test on the *next* unseen window, then roll forward.

    This is the honest version of a grid search. The parameters used on each test
    window were chosen without seeing it, so the combined out-of-sample curve is
    what the strategy would actually have produced had you run it that way.
    """
    if scorer not in SCORERS:
        raise ValueError(f"unknown scorer {scorer!r}; expected one of {', '.join(SCORERS)}")
    if not grid:
        raise ValueError("a parameter grid is required")
    if train_bars < 50 or test_bars < 10:
        raise ValueError("train_bars must be >= 50 and test_bars >= 10")

    warmup = get_strategy(strategy_name).warmup
    needed = train_bars + test_bars + warmup
    if len(candles) < needed:
        raise ValueError(
            f"not enough data for walk-forward: have {len(candles)} candles, need at "
            f"least {needed} for {train_bars} train + {test_bars} test bars "
            f"(plus {warmup} warmup)"
        )

    keys = sorted(grid)
    combinations = [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]
    score = SCORERS[scorer]

    result = WalkForwardResult(strategy=strategy_name, scorer=scorer)
    equity = config.execution.starting_cash
    curve: list[EquityPoint] = []
    trades: list[Trade] = []

    start = 0
    index = 0
    while start + train_bars + test_bars <= len(candles):
        train_end = start + train_bars
        test_end = min(train_end + test_bars, len(candles))

        best_params, best_metrics = _best_on(
            config, strategy_name, combinations, candles[start:train_end], symbol, score
        )
        if best_params is None:
            start += test_bars
            index += 1
            continue

        # Hand the test window its warmup bars so indicators are primed, but
        # trading still begins exactly at the start of unseen data.
        window_start = max(0, train_end - warmup)
        oos = _run(config, strategy_name, best_params, candles[window_start:test_end], symbol, equity)

        if oos is not None:
            result.windows.append(
                Window(
                    index=index, train_start=start, train_end=train_end, test_end=test_end,
                    params=best_params, in_sample=best_metrics, out_of_sample=oos.metrics,
                    start_equity=equity, end_equity=oos.metrics.ending_equity,
                )
            )
            # Only the unseen portion of the curve counts as out-of-sample.
            curve.extend(oos.equity_curve[warmup:] if window_start < train_end else oos.equity_curve)
            trades.extend(oos.trades)
            equity = oos.metrics.ending_equity

        start += test_bars
        index += 1

    if curve:
        result.combined = compute(curve, trades, config.timeframe)
        tested = candles[train_bars : result.windows[-1].test_end] if result.windows else []
        if tested:
            benchmark, _ = buy_and_hold(
                tested,
                starting_cash=config.execution.starting_cash,
                fee_rate=config.execution.fee_rate,
                slippage_pct=config.execution.slippage_pct,
                timeframe=config.timeframe,
            )
            result.benchmark = benchmark
            result.combined.benchmark_return_pct = benchmark.total_return_pct
            result.combined.benchmark_max_drawdown_pct = benchmark.max_drawdown_pct
    result.equity_curve = curve
    result.trades = trades
    return result


def _best_on(config, strategy_name, combinations, candles, symbol, score):
    """Grid-search a training window and return the winning parameters."""
    best_params, best_metrics, best_score = None, None, float("-inf")
    for params in combinations:
        run = _run(config, strategy_name, params, candles, symbol, config.execution.starting_cash)
        if run is None:
            continue
        value = score(run.metrics)
        if value > best_score:
            best_params, best_metrics, best_score = params, run.metrics, value
    return best_params, best_metrics


def _run(config: Config, strategy_name: str, params: dict, candles, symbol: str, cash: float):
    """Run one backtest, returning None if the configuration is unusable."""
    if cash <= 0:
        return None
    scoped = _with_cash(config, cash)
    try:
        strategy = get_strategy(strategy_name, **params)
        return Backtester(scoped, strategy).run(symbol, candles)
    except (ValueError, KeyError) as exc:
        log.debug("skipping %s: %s", params, exc)
        return None


def _with_cash(config: Config, cash: float) -> Config:
    """A shallow copy of the config with different starting capital."""
    import copy

    scoped = copy.deepcopy(config)
    scoped.execution.starting_cash = cash
    return scoped


# ======================================================================
# Significance: is this distinguishable from luck?
# ======================================================================
@dataclass
class BootstrapResult:
    """A confidence interval on total return, from resampling the trades."""

    samples: int
    median_return_pct: float
    low_return_pct: float      # 5th percentile
    high_return_pct: float     # 95th percentile
    probability_profitable: float
    observed_return_pct: float
    trade_count: int

    @property
    def interval_includes_zero(self) -> bool:
        """If zero sits inside the interval, the result is not distinguishable from break-even."""
        return self.low_return_pct <= 0 <= self.high_return_pct


def bootstrap_returns(
    trades: list[Trade], starting_equity: float, samples: int = 2000, seed: int = 7
) -> BootstrapResult | None:
    """Resample the trade sequence to see how much of the result was ordering luck.

    Each sample draws the same number of trades with replacement and compounds
    them. A wide interval spanning zero means the headline number is noise.
    """
    if not trades or starting_equity <= 0:
        return None

    # Per-trade returns on the equity at risk, so compounding is meaningful.
    returns = [t.net_pnl / starting_equity for t in trades]
    observed = (sum(returns)) * 100

    rng = random.Random(seed)
    totals = []
    for _ in range(samples):
        equity = 1.0
        for _ in range(len(returns)):
            equity *= 1 + returns[rng.randrange(len(returns))]
        totals.append((equity - 1) * 100)
    totals.sort()

    def percentile(p: float) -> float:
        index = min(len(totals) - 1, max(0, int(p * len(totals))))
        return totals[index]

    return BootstrapResult(
        samples=samples,
        median_return_pct=percentile(0.5),
        low_return_pct=percentile(0.05),
        high_return_pct=percentile(0.95),
        probability_profitable=sum(1 for t in totals if t > 0) / len(totals),
        observed_return_pct=observed,
        trade_count=len(trades),
    )


@dataclass
class RandomBaselineResult:
    """How the strategy compares to trading the same amount, at random."""

    iterations: int
    strategy_return_pct: float
    median_random_return_pct: float
    percentile: float          # share of random runs the strategy beat
    beat_count: int
    trade_count: int
    holding_bars: int

    @property
    def p_value(self) -> float:
        """Share of random runs that did at least as well as the strategy."""
        return 1.0 - self.percentile

    @property
    def significant(self) -> bool:
        """Beat 95% of random traders with the same trade count and holding period."""
        return self.percentile >= 0.95


def random_entry_baseline(
    candles: list[Candle],
    trade_count: int,
    holding_bars: int,
    *,
    strategy_return_pct: float,
    fee_rate: float = 0.001,
    slippage_pct: float = 0.0005,
    iterations: int = 1000,
    seed: int = 7,
) -> RandomBaselineResult | None:
    """Compare against a trader who enters at random but trades just as often.

    This is the check that catches a "strategy" which is really just exposure to
    a rising market. If random entries with the same frequency and holding period
    do as well, the logic is not what made the money.
    """
    if trade_count <= 0 or holding_bars <= 0 or len(candles) <= holding_bars + 1:
        return None

    rng = random.Random(seed)
    latest = len(candles) - holding_bars - 1
    if latest <= 0:
        return None

    totals = []
    for _ in range(iterations):
        total = 0.0
        for _ in range(trade_count):
            start = rng.randrange(latest)
            entry = candles[start].open * (1 + slippage_pct)
            exit_price = candles[start + holding_bars].close * (1 - slippage_pct)
            if entry <= 0:
                continue
            # Same cost model as a real trade: a fee on each side.
            total += (exit_price / entry) * (1 - fee_rate) ** 2 - 1
        totals.append(total * 100)

    beat = sum(1 for t in totals if strategy_return_pct > t)
    totals.sort()
    return RandomBaselineResult(
        iterations=iterations,
        strategy_return_pct=strategy_return_pct,
        median_random_return_pct=totals[len(totals) // 2],
        percentile=beat / len(totals),
        beat_count=beat,
        trade_count=trade_count,
        holding_bars=holding_bars,
    )


def average_holding_bars(trades: list[Trade], timeframe: str) -> int:
    """Mean bars held per trade, for matching the random baseline's exposure."""
    from .data.feed import TIMEFRAME_MINUTES

    if not trades:
        return 0
    minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    total = sum((t.closed_at - t.opened_at).total_seconds() / 60 for t in trades)
    return max(1, round(total / len(trades) / minutes))


# ======================================================================
# Cost sensitivity
# ======================================================================
@dataclass
class CostPoint:
    fee_rate: float
    total_return_pct: float
    trades: int


@dataclass
class CostSensitivityResult:
    points: list[CostPoint] = field(default_factory=list)

    @property
    def breakeven_fee(self) -> float | None:
        """The fee level at which the strategy stops making money.

        A strategy whose breakeven sits near real-world fees is not tradable,
        however good it looks at zero cost.
        """
        profitable = [p for p in self.points if p.total_return_pct > 0]
        if not profitable:
            return None
        return max(p.fee_rate for p in profitable)


def cost_sensitivity(
    config: Config,
    strategy: Strategy,
    candles: list[Candle],
    *,
    fee_levels: list[float] | None = None,
    symbol: str = "BTC/USDT",
) -> CostSensitivityResult:
    """Re-run across a range of fee assumptions to find where the edge dies."""
    levels = fee_levels or [0.0, 0.0005, 0.001, 0.0015, 0.002, 0.003, 0.005]
    result = CostSensitivityResult()

    for fee in levels:
        scoped = _with_cash(config, config.execution.starting_cash)
        scoped.execution.fee_rate = fee
        try:
            run = Backtester(scoped, strategy).run(symbol, candles)
        except ValueError:
            continue
        result.points.append(CostPoint(fee, run.metrics.total_return_pct, run.metrics.total_trades))
    return result
