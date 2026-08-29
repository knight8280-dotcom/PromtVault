"""The risk manager is what stands between a bad strategy and a blown account."""

from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.config import RiskConfig
from tradingbot.models import AccountState, Candle, Position, Side, Signal, SignalType
from tradingbot.risk import RiskManager

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def account(cash=10_000.0, equity=10_000.0, positions=None):
    return AccountState(cash=cash, equity=equity, positions=positions or {})


def long_signal(stop=None):
    return Signal(SignalType.ENTER_LONG, stop_price=stop)


def test_size_is_set_so_a_stop_loses_exactly_the_risk_budget():
    rm = RiskManager(
        RiskConfig(risk_per_trade=0.01, max_position_pct=1.0, max_total_exposure_pct=1.0)
    )
    decision = rm.size_entry(long_signal(stop=99.0), 100.0, account(), "BTC/USDT")
    # 1% of 10,000 = 100 risked, over a 1.0 stop distance = 100 units.
    assert decision.amount == pytest.approx(100.0)
    loss_if_stopped = (100.0 - 99.0) * decision.amount
    assert loss_if_stopped == pytest.approx(100.0)


def test_position_notional_is_capped_regardless_of_a_tight_stop():
    rm = RiskManager(RiskConfig(risk_per_trade=0.01, max_position_pct=0.2))
    # A very tight stop would otherwise justify an enormous position.
    decision = rm.size_entry(long_signal(stop=99.99), 100.0, account(), "BTC/USDT")
    assert decision.amount * 100.0 <= 10_000 * 0.2 + 1e-6


def test_size_never_exceeds_available_cash():
    rm = RiskManager(RiskConfig(risk_per_trade=0.1, max_position_pct=1.0))
    decision = rm.size_entry(long_signal(stop=99.9), 100.0, account(cash=500.0), "BTC/USDT")
    assert decision.amount * 100.0 <= 500.0 + 1e-6


def test_total_exposure_limit_blocks_a_third_position():
    rm = RiskManager(RiskConfig(max_total_exposure_pct=0.5, max_open_positions=5))
    held = {
        "ETH/USDT": Position("ETH/USDT", Side.BUY, 50.0, 100.0, NOW),
    }
    decision = rm.size_entry(long_signal(stop=95.0), 100.0, account(positions=held), "BTC/USDT")
    # 5,000 already deployed against a 5,000 ceiling leaves no headroom.
    assert not decision.approved
    assert "exposure" in decision.reason


def test_max_open_positions_is_enforced():
    rm = RiskManager(RiskConfig(max_open_positions=1))
    held = {"ETH/USDT": Position("ETH/USDT", Side.BUY, 1.0, 100.0, NOW)}
    decision = rm.size_entry(long_signal(), 100.0, account(positions=held), "BTC/USDT")
    assert not decision.approved
    assert "max open positions" in decision.reason


def test_duplicate_symbol_entry_is_rejected():
    rm = RiskManager(RiskConfig())
    held = {"BTC/USDT": Position("BTC/USDT", Side.BUY, 1.0, 100.0, NOW)}
    decision = rm.size_entry(long_signal(), 100.0, account(positions=held), "BTC/USDT")
    assert not decision.approved
    assert "already holding" in decision.reason


def test_shorts_are_rejected_unless_explicitly_enabled():
    rm = RiskManager(RiskConfig(allow_shorts=False))
    decision = rm.size_entry(Signal(SignalType.ENTER_SHORT), 100.0, account(), "BTC/USDT")
    assert not decision.approved

    rm = RiskManager(RiskConfig(allow_shorts=True))
    decision = rm.size_entry(Signal(SignalType.ENTER_SHORT), 100.0, account(), "BTC/USDT")
    assert decision.approved
    assert decision.stop_price > 100.0  # a short's stop sits above the entry


def test_a_stop_on_the_wrong_side_falls_back_to_the_configured_default():
    rm = RiskManager(RiskConfig(stop_loss_pct=0.02))
    # A "stop" above entry on a long is nonsense and must not be trusted.
    decision = rm.size_entry(long_signal(stop=105.0), 100.0, account(), "BTC/USDT")
    assert decision.stop_price == pytest.approx(98.0)


def test_orders_below_the_minimum_notional_are_rejected():
    rm = RiskManager(RiskConfig(risk_per_trade=0.001), min_order_notional=1_000.0)
    decision = rm.size_entry(long_signal(stop=50.0), 100.0, account(), "BTC/USDT")
    assert not decision.approved
    assert "minimum order notional" in decision.reason


def test_drawdown_breach_halts_trading():
    rm = RiskManager(RiskConfig(max_drawdown_pct=0.2))
    rm.observe_equity(10_000, NOW)
    rm.observe_equity(8_500, NOW)
    assert not rm.is_halted
    rm.observe_equity(7_900, NOW)  # 21% below peak
    assert rm.is_halted
    assert "drawdown" in rm.halt_reason
    assert not rm.size_entry(long_signal(), 100.0, account(), "BTC/USDT").approved


def test_daily_loss_limit_halts_trading():
    rm = RiskManager(RiskConfig(max_daily_loss_pct=0.05))
    rm.observe_equity(10_000, NOW)
    rm.record_realized_pnl(-300, 10_000)
    assert not rm.is_halted
    rm.record_realized_pnl(-300, 10_000)  # -600 total, past the 500 cap
    assert rm.is_halted
    assert "daily loss" in rm.halt_reason


def test_a_new_day_clears_a_daily_halt_but_not_a_drawdown_halt():
    rm = RiskManager(RiskConfig(max_daily_loss_pct=0.05))
    rm.observe_equity(10_000, NOW)
    rm.record_realized_pnl(-600, 10_000)
    assert rm.is_halted

    rm.observe_equity(10_000, NOW + timedelta(days=1))
    assert not rm.is_halted
    assert rm.realized_today == 0

    rm2 = RiskManager(RiskConfig(max_drawdown_pct=0.1))
    rm2.observe_equity(10_000, NOW)
    rm2.observe_equity(8_000, NOW)
    rm2.observe_equity(8_000, NOW + timedelta(days=1))
    assert rm2.is_halted  # a drawdown halt must survive the day roll


def test_stop_is_checked_before_take_profit_on_a_bar_that_spans_both():
    rm = RiskManager(RiskConfig())
    position = Position("BTC/USDT", Side.BUY, 1.0, 100.0, NOW, stop_price=95.0, take_profit_price=105.0)
    both = Candle(NOW, 100.0, 106.0, 94.0, 100.0, 1.0)
    # We cannot know the intra-bar order, so assume the worse outcome.
    assert rm.check_protective_exit(position, both) == "stop loss"


def test_trailing_stop_only_ever_ratchets_upward_on_a_long():
    rm = RiskManager(RiskConfig(trailing_stop_pct=0.05))
    position = Position("BTC/USDT", Side.BUY, 1.0, 100.0, NOW, stop_price=95.0)

    assert rm.update_trailing_stop(position, 110.0)
    assert position.stop_price == pytest.approx(104.5)

    assert not rm.update_trailing_stop(position, 90.0)
    assert position.stop_price == pytest.approx(104.5)


def test_a_gap_through_the_stop_fills_below_it():
    rm = RiskManager(RiskConfig())
    position = Position("BTC/USDT", Side.BUY, 1.0, 100.0, NOW, stop_price=95.0)
    gapped = Candle(NOW, 90.0, 92.0, 88.0, 91.0, 1.0)
    # The market opened below the stop; we do not get filled at 95.
    assert rm.exit_fill_price(position, gapped, "stop loss") == pytest.approx(90.0)


def test_zero_equity_is_rejected_rather_than_dividing_by_zero():
    rm = RiskManager(RiskConfig())
    decision = rm.size_entry(long_signal(), 100.0, account(cash=0, equity=0), "BTC/USDT")
    assert not decision.approved


def test_resume_clears_a_halt():
    rm = RiskManager(RiskConfig(max_drawdown_pct=0.1))
    rm.observe_equity(10_000, NOW)
    rm.observe_equity(8_000, NOW)
    assert rm.is_halted
    rm.resume()
    assert not rm.is_halted
