"""Regime detection, and the rule that exits are never gated."""

import pytest

from tradingbot.models import HOLD, Position, Side, Signal, SignalType
from tradingbot.regime import (
    Regime,
    RegimeDetector,
    RegimeGatedStrategy,
    efficiency_ratio,
    normalized_atr,
    regime_summary,
)
from tradingbot.strategies.base import Strategy

from .conftest import START, make_candles


# ------------------------------------------------------------- efficiency
def test_a_straight_line_is_perfectly_efficient():
    assert efficiency_ratio([1, 2, 3, 4, 5, 6], 5) == pytest.approx(1.0)


def test_a_perfect_zigzag_is_inefficient():
    assert efficiency_ratio([1, 2, 1, 2, 1, 2], 5) < 0.3


def test_a_round_trip_has_zero_efficiency():
    """Ending where you started means no net movement, however far you travelled."""
    assert efficiency_ratio([1, 5, 1], 2) == pytest.approx(0.0)


def test_a_flat_series_is_zero_not_an_error():
    assert efficiency_ratio([5, 5, 5, 5], 3) == 0.0


def test_efficiency_needs_a_full_window():
    assert efficiency_ratio([1, 2], 10) is None


def test_normalized_atr_is_a_fraction_of_price():
    candles = make_candles([100.0] * 40, spread=0.01)
    value = normalized_atr(candles, 14)
    assert value is not None and 0 < value < 1


# --------------------------------------------------------------- detection
def test_a_steady_climb_reads_as_trending():
    reading = RegimeDetector(period=20).detect(make_candles([100 + i for i in range(60)]))
    assert reading.regime is Regime.TRENDING
    assert reading.is_trending and reading.tradable_for_trend


def test_an_oscillating_market_reads_as_choppy_not_trending():
    candles = make_candles([100 + (i % 2) * 3 for i in range(120)])
    reading = RegimeDetector(period=20).detect(candles)
    assert reading.regime in (Regime.CHOPPY, Regime.QUIET, Regime.VOLATILE)
    assert not reading.is_trending
    assert reading.tradable_for_reversion


def test_too_little_data_reads_as_unknown():
    reading = RegimeDetector(period=30).detect(make_candles([100.0] * 5))
    assert reading.regime is Regime.UNKNOWN
    assert not reading.tradable_for_trend


def test_every_reading_explains_itself():
    for closes in ([100 + i for i in range(60)], [100 + (i % 2) for i in range(120)]):
        assert RegimeDetector(period=20).detect(make_candles(closes)).reason


def test_thresholds_must_be_ordered():
    with pytest.raises(ValueError, match="chop_threshold"):
        RegimeDetector(trend_threshold=0.1, chop_threshold=0.5)


def test_a_summary_covers_the_whole_dataset():
    candles = make_candles([100 + i * 0.5 for i in range(400)])
    summary = regime_summary(candles, RegimeDetector(period=20))
    assert summary
    assert sum(summary.values()) == pytest.approx(1.0)


# ------------------------------------------------------------------ gating
class AlwaysEnters(Strategy):
    name = "_test_always_enters"
    default_params: dict = {}

    @property
    def warmup(self):
        return 2

    def generate(self, candles, position):
        if position is None:
            return Signal(SignalType.ENTER_LONG, reason="always")
        return Signal(SignalType.EXIT, reason="always exits")


def a_position():
    return Position("BTC/USDT", Side.BUY, 1.0, 100.0, START)


def test_entries_are_blocked_in_the_wrong_regime():
    gated = RegimeGatedStrategy(AlwaysEnters(), RegimeDetector(period=20), allow="trend")
    choppy = make_candles([100 + (i % 2) for i in range(150)])
    signal = gated.generate(choppy, None)
    assert signal.type is SignalType.HOLD
    assert "regime" in signal.reason
    assert sum(gated.blocked_entries.values()) == 1


def test_entries_pass_through_in_the_right_regime():
    gated = RegimeGatedStrategy(AlwaysEnters(), RegimeDetector(period=20), allow="trend")
    trending = make_candles([100 + i for i in range(80)])
    assert gated.generate(trending, None).type is SignalType.ENTER_LONG
    assert not gated.blocked_entries


def test_exits_are_never_blocked():
    """A position opened in one regime must stay closable in another."""
    gated = RegimeGatedStrategy(AlwaysEnters(), RegimeDetector(period=20), allow="trend")
    choppy = make_candles([100 + (i % 2) for i in range(150)])
    assert gated.generate(choppy, a_position()).type is SignalType.EXIT


def test_an_unknown_regime_blocks_entries():
    """No reading means no confidence, so no new risk."""
    gated = RegimeGatedStrategy(AlwaysEnters(), RegimeDetector(period=30), allow="trend")
    assert gated.generate(make_candles([100.0] * 8), None).type is SignalType.HOLD


def test_allow_any_never_blocks():
    gated = RegimeGatedStrategy(AlwaysEnters(), RegimeDetector(period=20), allow="any")
    choppy = make_candles([100 + (i % 2) for i in range(150)])
    assert gated.generate(choppy, None).type is SignalType.ENTER_LONG


def test_reversion_gating_is_the_mirror_of_trend_gating():
    trending = make_candles([100 + i for i in range(80)])
    reversion = RegimeGatedStrategy(AlwaysEnters(), RegimeDetector(period=20), allow="reversion")
    assert reversion.generate(trending, None).type is SignalType.HOLD


def test_an_unknown_allow_mode_is_rejected():
    with pytest.raises(ValueError, match="allow must be"):
        RegimeGatedStrategy(AlwaysEnters(), allow="sideways")


def test_gating_widens_warmup_to_cover_both_needs():
    inner = AlwaysEnters()
    detector = RegimeDetector(period=50, volatility_lookback=200)
    gated = RegimeGatedStrategy(inner, detector)
    assert gated.warmup >= detector.warmup
    assert gated.warmup >= inner.warmup


def test_a_gated_strategy_runs_in_a_backtest(config):
    from tradingbot.backtest import Backtester
    from tradingbot.data import generate_synthetic
    from tradingbot.strategies import get_strategy

    inner = get_strategy("sma_cross", fast_period=10, slow_period=30)
    gated = RegimeGatedStrategy(inner, RegimeDetector(period=20), allow="trend")
    result = Backtester(config, gated).run("BTC/USDT", generate_synthetic(bars=1500, seed=3))
    assert result.metrics.benchmark_return_pct is not None
    assert "regime_gated" in result.strategy


def test_gating_reduces_trade_count(config):
    """Blocking entries must actually mean fewer trades, not just a label."""
    from tradingbot.backtest import Backtester
    from tradingbot.data import generate_synthetic
    from tradingbot.strategies import get_strategy

    candles = generate_synthetic(bars=2000, seed=7)
    ungated = Backtester(config, get_strategy("sma_cross", fast_period=10, slow_period=30)).run(
        "BTC/USDT", candles
    )
    gated = Backtester(
        config,
        RegimeGatedStrategy(
            get_strategy("sma_cross", fast_period=10, slow_period=30),
            RegimeDetector(period=20), allow="trend",
        ),
    ).run("BTC/USDT", candles)
    assert gated.metrics.total_trades <= ungated.metrics.total_trades
