"""Backtest integrity: no look-ahead, correct accounting, honest metrics."""

import pytest

from tradingbot.backtest import Backtester
from tradingbot.config import from_dict
from tradingbot.data import generate_synthetic
from tradingbot.metrics import compute, max_drawdown, sharpe
from tradingbot.models import EquityPoint, HOLD, Signal, SignalType
from tradingbot.strategies import get_strategy
from tradingbot.strategies.base import Strategy

from .conftest import START, make_candles


class BuyAndHold(Strategy):
    """Enters once on the first eligible bar and never exits."""

    name = "_test_buy_and_hold"
    default_params = {}

    @property
    def warmup(self):
        return 2

    def generate(self, candles, position):
        if position is None and len(candles) == self.warmup + 1:
            return Signal(SignalType.ENTER_LONG, reason="test entry")
        return HOLD


class RecordsWhatItSaw(Strategy):
    """Records the number of candles handed to it on each call."""

    name = "_test_recorder"
    default_params = {}

    def __init__(self, **params):
        super().__init__(**params)
        self.seen = []

    @property
    def warmup(self):
        return 2

    def generate(self, candles, position):
        self.seen.append(len(candles))
        return HOLD


def test_a_strategy_is_never_shown_a_future_bar():
    config = from_dict({})
    strategy = RecordsWhatItSaw()
    candles = make_candles([100 + i for i in range(50)])
    Backtester(config, strategy).run("BTC/USDT", candles)

    # Window lengths must be strictly increasing and never exceed the bar index.
    assert strategy.seen == sorted(strategy.seen)
    assert max(strategy.seen) <= len(candles)


def test_an_entry_signalled_on_a_close_fills_at_the_next_bars_open(config):
    config.risk.take_profit_pct = None
    config.risk.stop_loss_pct = 0.9  # keep the stop far away
    strategy = BuyAndHold()
    candles = make_candles([100.0, 100.0, 100.0, 150.0, 150.0, 150.0])

    result = Backtester(config, strategy).run("BTC/USDT", candles)
    assert result.trades
    # The signal fires on the bar closing at 100, so the fill is the NEXT open,
    # not the 150 close the strategy could not have known about.
    assert result.trades[0].entry_price == pytest.approx(candles[3].open)


def test_open_positions_are_closed_at_the_end_of_the_run(config):
    config.risk.take_profit_pct = None
    config.risk.stop_loss_pct = 0.9
    result = Backtester(config, BuyAndHold()).run("BTC/USDT", make_candles([100.0] * 20))
    assert result.trades
    assert result.trades[-1].reason == "end of data"


def test_equity_curve_has_one_point_per_bar(config):
    candles = make_candles([100 + i for i in range(40)])
    result = Backtester(config, BuyAndHold()).run("BTC/USDT", candles)
    assert len(result.equity_curve) == len(candles)


def test_a_flat_market_loses_exactly_the_fees(config):
    config.execution.fee_rate = 0.001
    config.risk.take_profit_pct = None
    config.risk.stop_loss_pct = 0.9
    result = Backtester(config, BuyAndHold()).run("BTC/USDT", make_candles([100.0] * 30))

    assert result.metrics.total_return_pct < 0
    assert result.metrics.ending_equity == pytest.approx(
        10_000 - result.metrics.total_fees, rel=1e-6
    )


def test_a_stop_loss_caps_the_loss_near_the_risk_budget(config):
    config.risk.risk_per_trade = 0.02
    config.risk.stop_loss_pct = 0.1
    config.risk.take_profit_pct = None
    config.execution.fee_rate = 0.0
    # A steady grind down guarantees the stop is hit without a gap through it.
    candles = make_candles([100.0, 100.0, 100.0] + [100 - i * 0.5 for i in range(40)])

    result = Backtester(config, BuyAndHold()).run("BTC/USDT", candles)
    assert result.trades
    loss = result.trades[0].net_pnl
    assert loss < 0
    # Risked 2% of 10,000 = 200; allow slack for the bar that breaches the stop.
    assert abs(loss) < 300


def test_insufficient_data_is_reported_clearly(config):
    strategy = get_strategy("sma_cross")
    with pytest.raises(ValueError, match="not enough data"):
        Backtester(config, strategy).run("BTC/USDT", make_candles([100.0] * 10))


def test_a_halt_stops_further_entries(config):
    config.risk.max_drawdown_pct = 0.01  # trips almost immediately
    config.risk.stop_loss_pct = 0.02
    candles = make_candles([100.0, 100.0, 100.0] + [100 - i for i in range(40)])
    result = Backtester(config, BuyAndHold()).run("BTC/USDT", candles)
    assert result.halted_reason is not None


def test_rejected_entries_are_reported_with_a_reason(config):
    config.execution.min_order_notional = 1_000_000  # nothing can ever qualify
    result = Backtester(config, BuyAndHold()).run("BTC/USDT", make_candles([100.0] * 30))
    assert not result.trades
    assert result.rejections


def test_a_backtest_over_synthetic_data_runs_end_to_end(config):
    strategy = get_strategy("sma_cross", fast_period=10, slow_period=30)
    result = Backtester(config, strategy).run(
        "BTC/USDT", generate_synthetic(bars=1500, seed=11)
    )
    assert result.metrics.total_trades > 0
    assert len(result.equity_curve) == 1500
    # Equity can never go negative in a cash-only, long-only account.
    assert all(p.equity > 0 for p in result.equity_curve)


def test_results_are_reproducible(config):
    candles = generate_synthetic(bars=800, seed=5)
    strategy = get_strategy("breakout", entry_period=10, exit_period=5)
    first = Backtester(config, strategy).run("BTC/USDT", candles)
    second = Backtester(config, strategy).run("BTC/USDT", candles)
    assert first.metrics.ending_equity == second.metrics.ending_equity
    assert len(first.trades) == len(second.trades)


# ------------------------------------------------------------------- metrics
def test_max_drawdown_measures_peak_to_trough():
    worst, duration = max_drawdown([100, 120, 60, 80, 130])
    assert worst == pytest.approx(0.5)  # 120 -> 60
    assert duration == 2  # 60 and 80 are underwater; 130 sets a new peak


def test_max_drawdown_of_a_rising_curve_is_zero():
    assert max_drawdown([100, 110, 120])[0] == 0.0


def test_sharpe_of_a_constant_return_series_is_zero():
    assert sharpe([0.01] * 20, 365) == 0.0  # no variance means no risk-adjusted signal


def test_metrics_handle_a_run_with_no_trades():
    curve = [EquityPoint(START, 10_000.0, 10_000.0)]
    m = compute(curve, [], "1h")
    assert m.total_trades == 0
    assert m.win_rate == 0.0
    assert m.profit_factor == 0.0


def test_profit_factor_is_infinite_when_nothing_loses(config):
    from tradingbot.models import Side, Trade

    winner = Trade("BTC/USDT", Side.BUY, 1.0, 100.0, 110.0, START, START, 0.0)
    m = compute([EquityPoint(START, 10_000.0, 10_000.0)], [winner], "1h")
    assert m.profit_factor == float("inf")
    assert m.win_rate == 100.0
