"""Indicator correctness, including the padding contract every strategy relies on."""

import pytest

from tradingbot.indicators import (
    atr,
    bollinger,
    ema,
    rolling_max,
    rolling_min,
    rsi,
    sma,
    stddev,
)


def test_sma_matches_hand_calculation():
    values = [1, 2, 3, 4, 5]
    assert sma(values, 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_output_is_aligned_with_input():
    values = list(range(50))
    assert len(sma(values, 10)) == len(values)


def test_sma_pads_until_it_has_enough_data():
    assert sma([1, 2], 5) == [None, None]


def test_sma_rejects_bad_period():
    with pytest.raises(ValueError):
        sma([1, 2, 3], 0)


def test_ema_is_seeded_from_the_first_sma():
    values = [1, 2, 3, 4, 5, 6]
    result = ema(values, 3)
    assert result[2] == pytest.approx(2.0)  # SMA of 1,2,3
    # Then k = 2/(3+1) = 0.5, so next = 4*0.5 + 2*0.5 = 3.0
    assert result[3] == pytest.approx(3.0)


def test_ema_reacts_faster_than_sma():
    values = [10] * 20 + [20] * 5
    assert ema(values, 10)[-1] > sma(values, 10)[-1]


def test_rsi_is_100_when_price_only_rises():
    assert rsi(list(range(1, 30)), 14)[-1] == pytest.approx(100.0)


def test_rsi_is_zero_when_price_only_falls():
    assert rsi(list(range(30, 1, -1)), 14)[-1] == pytest.approx(0.0)


def test_rsi_stays_within_bounds():
    import random

    rng = random.Random(1)
    values = [100.0]
    for _ in range(200):
        values.append(values[-1] * (1 + rng.uniform(-0.05, 0.05)))
    for value in rsi(values, 14):
        assert value is None or 0 <= value <= 100


def test_atr_of_constant_range_equals_that_range():
    highs = [11.0] * 30
    lows = [10.0] * 30
    closes = [10.5] * 30
    assert atr(highs, lows, closes, 14)[-1] == pytest.approx(1.0)


def test_atr_accounts_for_gaps():
    # A gap up makes the true range larger than the bar's own high-low.
    highs = [10, 10, 20]
    lows = [9, 9, 19]
    closes = [9.5, 9.5, 19.5]
    from tradingbot.indicators import true_range

    assert true_range(highs, lows, closes)[-1] == pytest.approx(10.5)


def test_bollinger_bands_straddle_the_middle():
    values = [10, 12, 11, 13, 12, 14, 13, 15]
    lower, middle, upper = bollinger(values, 4, 2.0)
    assert lower[-1] < middle[-1] < upper[-1]


def test_stddev_of_constant_series_is_zero():
    assert stddev([5.0] * 10, 4)[-1] == pytest.approx(0.0)


def test_rolling_extremes():
    values = [3, 1, 4, 1, 5, 9, 2, 6]
    assert rolling_max(values, 3)[-1] == 9
    assert rolling_min(values, 3)[-1] == 2


def test_indicators_handle_empty_input():
    assert sma([], 3) == []
    assert rsi([], 14) == []
    assert atr([], [], [], 14) == []
