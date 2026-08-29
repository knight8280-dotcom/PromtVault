"""Validation tooling: the checks that decide whether a backtest means anything."""

import pytest

from tradingbot.backtest import Backtester
from tradingbot.data import generate_synthetic
from tradingbot.metrics import buy_and_hold
from tradingbot.models import Side, Trade
from tradingbot.strategies import get_strategy
from tradingbot.validation import (
    average_holding_bars,
    bootstrap_returns,
    cost_sensitivity,
    random_entry_baseline,
    walk_forward,
)

from .conftest import START, make_candles


# ------------------------------------------------------------- benchmark
def test_buy_and_hold_tracks_the_price_move():
    candles = make_candles([100.0, 110.0, 120.0, 200.0])
    m, curve = buy_and_hold(candles, 10_000.0, fee_rate=0.0, slippage_pct=0.0)
    # Bought at the first open (100), sold at the last close (200).
    assert m.total_return_pct == pytest.approx(100.0, rel=1e-6)
    assert len(curve) == len(candles)


def test_buy_and_hold_in_a_flat_market_loses_only_the_fees():
    candles = make_candles([100.0] * 50)
    m, _ = buy_and_hold(candles, 10_000.0, fee_rate=0.001, slippage_pct=0.0)
    assert m.total_return_pct < 0
    assert m.total_return_pct == pytest.approx(-0.2, abs=0.02)  # roughly two fees


def test_buy_and_hold_charges_slippage_against_you():
    candles = make_candles([100.0] * 20)
    clean, _ = buy_and_hold(candles, 10_000.0, fee_rate=0.0, slippage_pct=0.0)
    slipped, _ = buy_and_hold(candles, 10_000.0, fee_rate=0.0, slippage_pct=0.01)
    assert slipped.total_return_pct < clean.total_return_pct


def test_a_very_short_span_is_not_annualised_into_nonsense():
    """Compounding a few hours out to a year overflows and means nothing."""
    m, _ = buy_and_hold(make_candles([100.0, 200.0, 400.0, 800.0]), 10_000.0,
                        fee_rate=0.0, slippage_pct=0.0)
    assert m.total_return_pct == pytest.approx(700.0, rel=1e-6)
    assert m.annualized_return_pct == 0.0  # left alone rather than exploded


def test_buy_and_hold_handles_no_data():
    m, curve = buy_and_hold([], 10_000.0)
    assert curve == []
    assert m.total_return_pct == 0.0


def test_every_backtest_reports_the_benchmark(config):
    """An absolute return without the passive alternative is misleading."""
    strategy = get_strategy("sma_cross", fast_period=10, slow_period=30)
    result = Backtester(config, strategy).run("BTC/USDT", generate_synthetic(bars=1200, seed=3))

    m = result.metrics
    assert m.benchmark_return_pct is not None
    assert m.benchmark_max_drawdown_pct is not None
    assert m.excess_return_pct == pytest.approx(m.total_return_pct - m.benchmark_return_pct)
    assert m.beat_benchmark is (m.excess_return_pct > 0)
    assert len(result.benchmark_curve) == 1200


def test_a_strategy_beating_a_falling_market_shows_positive_excess(config):
    """Sitting in cash through a crash should read as beating buy and hold."""
    candles = make_candles([100 - i * 0.5 for i in range(300)])
    strategy = get_strategy("breakout", entry_period=20, exit_period=10)
    result = Backtester(config, strategy).run("BTC/USDT", candles)
    assert result.metrics.benchmark_return_pct < 0
    assert result.metrics.excess_return_pct > 0


def test_the_benchmark_appears_in_the_report(config):
    from tradingbot.metrics import format_report

    strategy = get_strategy("sma_cross", fast_period=10, slow_period=30)
    result = Backtester(config, strategy).run("BTC/USDT", generate_synthetic(bars=900, seed=2))
    report = format_report(result.metrics)
    assert "Buy and hold" in report
    assert "Excess vs holding" in report


def test_metrics_serialise_the_derived_comparison(config):
    strategy = get_strategy("sma_cross", fast_period=10, slow_period=30)
    result = Backtester(config, strategy).run("BTC/USDT", generate_synthetic(bars=900, seed=2))
    payload = result.metrics.as_dict()
    assert "excess_return_pct" in payload and "beat_benchmark" in payload


# ------------------------------------------------------------- bootstrap
def trades_with(pnls, entry=100.0):
    return [
        Trade("BTC/USDT", Side.BUY, 1.0, entry, entry + p, START, START, 0.0)
        for p in pnls
    ]


def test_bootstrap_brackets_the_observed_result():
    boot = bootstrap_returns(trades_with([50, -20, 30, -10, 40] * 6), 10_000.0, samples=800)
    assert boot is not None
    assert boot.low_return_pct < boot.median_return_pct < boot.high_return_pct
    assert 0 <= boot.probability_profitable <= 1


def test_a_consistently_profitable_series_excludes_zero():
    boot = bootstrap_returns(trades_with([200] * 40), 10_000.0, samples=800)
    assert not boot.interval_includes_zero
    assert boot.probability_profitable == 1.0


def test_a_coin_flip_series_spans_zero():
    """Wins and losses that cancel must not look like an edge."""
    boot = bootstrap_returns(trades_with([100, -100] * 25), 10_000.0, samples=1500)
    assert boot.interval_includes_zero


def test_bootstrap_is_reproducible():
    trades = trades_with([50, -20, 30] * 8)
    a = bootstrap_returns(trades, 10_000.0, samples=500, seed=42)
    b = bootstrap_returns(trades, 10_000.0, samples=500, seed=42)
    assert a.median_return_pct == b.median_return_pct


def test_bootstrap_needs_trades():
    assert bootstrap_returns([], 10_000.0) is None


# -------------------------------------------------------- random baseline
def test_a_strategy_matching_random_is_not_significant():
    candles = generate_synthetic(bars=1500, seed=5)
    baseline = random_entry_baseline(candles, 30, 10, strategy_return_pct=0.0, iterations=400)
    assert baseline is not None
    assert not baseline.significant  # a zero return cannot beat 95% of random runs


def test_an_extraordinary_return_beats_every_random_run():
    candles = generate_synthetic(bars=1500, seed=5)
    baseline = random_entry_baseline(candles, 30, 10, strategy_return_pct=10_000.0, iterations=300)
    assert baseline.percentile == 1.0
    assert baseline.significant
    assert baseline.p_value == 0.0


def test_the_baseline_matches_the_strategys_trade_count_and_holding():
    candles = generate_synthetic(bars=1500, seed=5)
    baseline = random_entry_baseline(candles, 25, 12, strategy_return_pct=1.0, iterations=200)
    assert baseline.trade_count == 25
    assert baseline.holding_bars == 12


def test_the_baseline_is_skipped_when_there_is_nothing_to_compare():
    candles = generate_synthetic(bars=100, seed=1)
    assert random_entry_baseline(candles, 0, 10, strategy_return_pct=1.0) is None
    assert random_entry_baseline(candles, 10, 0, strategy_return_pct=1.0) is None


def test_average_holding_is_measured_in_bars(config):
    strategy = get_strategy("breakout", entry_period=10, exit_period=5)
    result = Backtester(config, strategy).run("BTC/USDT", generate_synthetic(bars=1200, seed=8))
    if result.trades:
        assert average_holding_bars(result.trades, "1h") >= 1
    assert average_holding_bars([], "1h") == 0


# ------------------------------------------------------- cost sensitivity
def test_higher_fees_never_improve_returns(config):
    strategy = get_strategy("breakout", entry_period=15, exit_period=7)
    result = cost_sensitivity(config, strategy, generate_synthetic(bars=1200, seed=6))
    returns = [p.total_return_pct for p in result.points]
    assert len(returns) >= 5
    assert returns == sorted(returns, reverse=True)


def test_breakeven_fee_is_none_when_nothing_is_profitable(config):
    from tradingbot.validation import CostPoint, CostSensitivityResult

    losing = CostSensitivityResult([CostPoint(0.0, -5.0, 3), CostPoint(0.001, -8.0, 3)])
    assert losing.breakeven_fee is None

    mixed = CostSensitivityResult([CostPoint(0.0, 5.0, 3), CostPoint(0.001, 2.0, 3), CostPoint(0.002, -1.0, 3)])
    assert mixed.breakeven_fee == 0.001


# --------------------------------------------------------- walk forward
def test_walk_forward_produces_windows_and_a_combined_curve(config):
    candles = generate_synthetic(bars=2500, seed=9)
    wf = walk_forward(config, "sma_cross", {"fast_period": [10, 20], "slow_period": [30, 50]},
                      candles, train_bars=800, test_bars=300)
    assert len(wf.windows) >= 3
    assert wf.combined is not None
    assert wf.equity_curve
    assert all(w.params for w in wf.windows)


def test_walk_forward_test_windows_do_not_overlap(config):
    """Each test window must be unseen data, not a re-run of earlier bars."""
    candles = generate_synthetic(bars=2500, seed=9)
    wf = walk_forward(config, "sma_cross", {"fast_period": [10, 20]}, candles,
                      train_bars=800, test_bars=300)
    starts = [w.train_end for w in wf.windows]
    ends = [w.test_end for w in wf.windows]
    for i in range(1, len(starts)):
        assert starts[i] >= ends[i - 1], "test windows overlap — results would double-count"


def test_walk_forward_never_optimises_on_the_window_it_reports(config):
    """The out-of-sample number must differ from the in-sample one it was picked by."""
    candles = generate_synthetic(bars=2500, seed=9)
    wf = walk_forward(config, "sma_cross", {"fast_period": [5, 10, 20], "slow_period": [30, 50]},
                      candles, train_bars=800, test_bars=300)
    identical = [w for w in wf.windows
                 if w.in_sample.total_return_pct == w.out_of_sample.total_return_pct != 0]
    assert not identical, "in-sample and out-of-sample results match — the split leaked"


def test_walk_forward_reports_parameter_stability(config):
    candles = generate_synthetic(bars=2500, seed=9)
    wf = walk_forward(config, "sma_cross", {"fast_period": [5, 10, 20]}, candles,
                      train_bars=800, test_bars=300)
    stability = wf.parameter_stability
    assert "fast_period" in stability
    assert 1 <= stability["fast_period"] <= 3


def test_walk_forward_compounds_equity_across_windows(config):
    candles = generate_synthetic(bars=2500, seed=9)
    wf = walk_forward(config, "sma_cross", {"fast_period": [10, 20]}, candles,
                      train_bars=800, test_bars=300)
    for i in range(1, len(wf.windows)):
        # Each window starts with what the previous one finished with.
        assert wf.windows[i].start_equity == pytest.approx(wf.windows[i - 1].end_equity)


def test_walk_forward_rejects_too_little_data(config):
    with pytest.raises(ValueError, match="not enough data"):
        walk_forward(config, "sma_cross", {"fast_period": [10]},
                     generate_synthetic(bars=200, seed=1), train_bars=800, test_bars=300)


def test_walk_forward_rejects_an_empty_grid(config):
    with pytest.raises(ValueError, match="grid is required"):
        walk_forward(config, "sma_cross", {}, generate_synthetic(bars=2000, seed=1))


def test_walk_forward_rejects_an_unknown_scorer(config):
    with pytest.raises(ValueError, match="unknown scorer"):
        walk_forward(config, "sma_cross", {"fast_period": [10]},
                     generate_synthetic(bars=2000, seed=1), scorer="vibes")


def test_walk_forward_is_reproducible(config):
    candles = generate_synthetic(bars=2200, seed=4)
    grid = {"fast_period": [10, 20]}
    a = walk_forward(config, "sma_cross", grid, candles, train_bars=800, test_bars=300)
    b = walk_forward(config, "sma_cross", grid, candles, train_bars=800, test_bars=300)
    assert a.out_of_sample_mean == b.out_of_sample_mean
    assert [w.params for w in a.windows] == [w.params for w in b.windows]
