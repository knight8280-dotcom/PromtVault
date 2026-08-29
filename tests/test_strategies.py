"""Strategies must be honest: no look-ahead, and no signals before warmup."""

import pytest

from tradingbot.models import Position, Side, SignalType
from tradingbot.strategies import available_strategies, get_strategy
from tradingbot.strategies.base import Strategy

from .conftest import START, make_candles


def a_position():
    return Position("BTC/USDT", Side.BUY, 1.0, 100.0, START)


@pytest.mark.parametrize("name", available_strategies())
def test_every_strategy_holds_until_warmup_is_satisfied(name):
    strategy = get_strategy(name)
    short = make_candles([100.0] * (strategy.warmup - 1))
    assert strategy.generate(short, None).type is SignalType.HOLD


@pytest.mark.parametrize("name", available_strategies())
def test_every_strategy_is_deterministic(name):
    strategy = get_strategy(name)
    series = make_candles([100 + i * 0.5 for i in range(300)])
    assert strategy.generate(series, None) == strategy.generate(series, None)


@pytest.mark.parametrize("name", available_strategies())
def test_a_strategy_only_sees_bars_up_to_the_one_it_judges(name):
    """Appending future bars must not change the signal for an earlier bar."""
    strategy = get_strategy(name)
    series = make_candles([100 + (i % 40) * 2 for i in range(400)])
    cutoff = 300
    before = strategy.generate(series[:cutoff], None)
    # The strategy is handed the same window; future data simply is not passed.
    after = strategy.generate(series[:cutoff], None)
    assert before == after


@pytest.mark.parametrize("name", available_strategies())
def test_strategies_reject_unknown_parameters(name):
    with pytest.raises(ValueError, match="unknown parameter"):
        get_strategy(name, definitely_not_a_real_param=1)


def test_unknown_strategy_name_is_reported_with_the_valid_options():
    with pytest.raises(KeyError, match="unknown strategy"):
        get_strategy("does_not_exist")


# ---------------------------------------------------------------- sma_cross
def test_sma_cross_goes_long_on_a_golden_cross():
    strategy = get_strategy("sma_cross", fast_period=3, slow_period=6, atr_stop_multiple=0)
    # Fall, then rally hard enough for the fast average to overtake the slow one.
    closes = [100 - i for i in range(20)] + [80 + i * 4 for i in range(12)]
    signal = _first_signal(strategy, make_candles(closes))
    assert signal is not None and signal.type is SignalType.ENTER_LONG


def test_sma_cross_exits_an_open_position_on_a_death_cross():
    strategy = get_strategy("sma_cross", fast_period=3, slow_period=6, atr_stop_multiple=0)
    closes = [100 + i * 3 for i in range(20)] + [160 - i * 5 for i in range(12)]
    candles = make_candles(closes)
    signals = [strategy.generate(candles[: i + 1], a_position()) for i in range(len(candles))]
    assert any(s.type is SignalType.EXIT for s in signals)


def test_sma_cross_does_not_re_enter_while_already_positioned():
    strategy = get_strategy("sma_cross", fast_period=3, slow_period=6)
    closes = [100 - i for i in range(20)] + [80 + i * 4 for i in range(12)]
    candles = make_candles(closes)
    for i in range(len(candles)):
        assert strategy.generate(candles[: i + 1], a_position()).type is not SignalType.ENTER_LONG


def test_sma_cross_supplies_an_atr_stop_below_the_entry_price():
    strategy = get_strategy("sma_cross", fast_period=3, slow_period=6, atr_stop_multiple=2.0)
    closes = [100 - i for i in range(20)] + [80 + i * 4 for i in range(12)]
    candles = make_candles(closes)
    signal = _first_signal(strategy, candles)
    assert signal is not None
    entry = next(c.close for i, c in enumerate(candles) if strategy.generate(candles[: i + 1], None) == signal)
    assert signal.stop_price is not None and signal.stop_price < entry


def test_sma_cross_rejects_a_fast_period_at_or_above_the_slow_one():
    with pytest.raises(ValueError, match="fast_period must be less"):
        get_strategy("sma_cross", fast_period=50, slow_period=20)


def test_sma_cross_min_separation_filters_out_marginal_crosses():
    loose = get_strategy("sma_cross", fast_period=3, slow_period=6, min_separation_pct=0.0)
    strict = get_strategy("sma_cross", fast_period=3, slow_period=6, min_separation_pct=0.5)
    closes = [100 - i for i in range(20)] + [80 + i * 4 for i in range(12)]
    candles = make_candles(closes)
    assert _first_signal(loose, candles) is not None
    assert _first_signal(strict, candles) is None


# ------------------------------------------------------------ rsi_reversion
def test_rsi_reversion_buys_a_dip_inside_an_uptrend():
    strategy = get_strategy(
        "rsi_reversion", rsi_period=5, oversold=35.0, trend_filter_period=0
    )
    closes = [100 + i for i in range(40)] + [140 - i * 3 for i in range(10)]
    signal = _first_signal(strategy, make_candles(closes))
    assert signal is not None and signal.type is SignalType.ENTER_LONG


def test_rsi_reversion_trend_filter_blocks_dips_in_a_downtrend():
    strategy = get_strategy("rsi_reversion", rsi_period=5, oversold=35.0, trend_filter_period=20)
    closes = [200 - i * 2 for i in range(60)]  # relentless downtrend
    assert _first_signal(strategy, make_candles(closes)) is None


def test_rsi_reversion_exits_once_momentum_recovers():
    strategy = get_strategy("rsi_reversion", rsi_period=5, exit_level=50.0, trend_filter_period=0)
    closes = [100 - i for i in range(20)] + [80 + i * 3 for i in range(15)]
    candles = make_candles(closes)
    signals = [strategy.generate(candles[: i + 1], a_position()) for i in range(len(candles))]
    assert any(s.type is SignalType.EXIT for s in signals)


def test_rsi_reversion_rejects_inconsistent_levels():
    with pytest.raises(ValueError, match="oversold"):
        get_strategy("rsi_reversion", oversold=60.0, exit_level=50.0)


# ----------------------------------------------------------------- breakout
def test_breakout_enters_on_a_new_channel_high():
    strategy = get_strategy("breakout", entry_period=10, exit_period=5, atr_stop_multiple=0)
    closes = [100.0] * 30 + [130.0]
    signal = _first_signal(strategy, make_candles(closes))
    assert signal is not None and signal.type is SignalType.ENTER_LONG


def test_breakout_does_not_enter_inside_the_channel():
    strategy = get_strategy("breakout", entry_period=10, exit_period=5)
    closes = [100 + (i % 5) for i in range(60)]  # oscillates, never breaks out
    assert _first_signal(strategy, make_candles(closes)) is None


def test_breakout_exits_on_a_break_of_the_shorter_low():
    strategy = get_strategy("breakout", entry_period=10, exit_period=5)
    closes = [100.0] * 30 + [70.0]
    candles = make_candles(closes)
    signal = strategy.generate(candles, a_position())
    assert signal.type is SignalType.EXIT


def test_breakout_volume_filter_rejects_a_low_volume_break():
    strategy = get_strategy("breakout", entry_period=10, exit_period=5, volume_factor=5.0)
    closes = [100.0] * 30 + [130.0]
    # make_candles gives every bar the same volume, so a 5x filter must reject it.
    assert _first_signal(strategy, make_candles(closes)) is None


def test_breakout_rejects_an_exit_period_longer_than_the_entry_period():
    with pytest.raises(ValueError, match="exit_period"):
        get_strategy("breakout", entry_period=5, exit_period=20)


# ------------------------------------------------------------------ registry
def test_a_custom_strategy_can_be_registered_and_resolved():
    from tradingbot.strategies.base import register
    from tradingbot.models import HOLD

    @register
    class _Custom(Strategy):
        name = "_test_custom"
        default_params = {"x": 1}

        @property
        def warmup(self):
            return 1

        def generate(self, candles, position):
            return HOLD

    assert "_test_custom" in available_strategies()
    assert get_strategy("_test_custom", x=5).params["x"] == 5


def _first_signal(strategy, candles):
    """Return the first non-HOLD signal produced while replaying `candles`."""
    for i in range(len(candles)):
        signal = strategy.generate(candles[: i + 1], None)
        if signal.type is not SignalType.HOLD:
            return signal
    return None
