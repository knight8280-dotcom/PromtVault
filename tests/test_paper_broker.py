"""Simulated execution must be honest about cash, fees and slippage."""

from datetime import datetime, timezone

import pytest

from tradingbot.exchange.paper import InsufficientFunds, PaperBroker
from tradingbot.models import Order, Side

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def broker(**kwargs):
    defaults = {"starting_cash": 10_000.0, "fee_rate": 0.0, "slippage_pct": 0.0}
    b = PaperBroker(**{**defaults, **kwargs})
    b.mark("BTC/USDT", 100.0)
    return b


def test_buying_deducts_notional_and_fee_from_cash():
    b = broker(fee_rate=0.001)
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    assert b.cash == pytest.approx(10_000 - 1_000 - 1.0)


def test_equity_is_unchanged_by_a_flat_round_trip_minus_fees():
    b = broker(fee_rate=0.001)
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    b.submit(Order("BTC/USDT", Side.SELL, 10.0), NOW)
    assert b.get_equity() == pytest.approx(10_000 - 2.0)  # one fee per side


def test_equity_tracks_an_unrealized_gain():
    b = broker()
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    b.mark("BTC/USDT", 120.0)
    assert b.get_equity() == pytest.approx(10_200.0)


def test_slippage_always_works_against_the_trader():
    b = broker(slippage_pct=0.01)
    fill = b.submit(Order("BTC/USDT", Side.BUY, 1.0), NOW)
    assert fill.price == pytest.approx(101.0)  # pay up when buying

    b.reference_price["BTC/USDT"] = 100.0
    fill = b.submit(Order("BTC/USDT", Side.SELL, 1.0), NOW)
    assert fill.price == pytest.approx(99.0)  # receive less when selling


def test_cannot_spend_more_cash_than_the_account_holds():
    b = broker(starting_cash=500.0)
    with pytest.raises(InsufficientFunds):
        b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)  # needs 1,000


def test_closing_records_a_trade_with_net_pnl():
    b = broker(fee_rate=0.001)
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    b.reference_price["BTC/USDT"] = 110.0
    b.submit(Order("BTC/USDT", Side.SELL, 10.0, client_id="take profit"), NOW)

    assert len(b.trades) == 1
    trade = b.trades[0]
    assert trade.gross_pnl == pytest.approx(100.0)
    assert trade.net_pnl == pytest.approx(100.0 - 1.0 - 1.1)
    assert trade.reason == "take profit"
    assert trade.is_win


def test_a_losing_trade_is_recorded_as_a_loss():
    b = broker()
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    b.reference_price["BTC/USDT"] = 90.0
    b.submit(Order("BTC/USDT", Side.SELL, 10.0), NOW)
    assert b.trades[0].net_pnl == pytest.approx(-100.0)
    assert not b.trades[0].is_win


def test_a_short_round_trip_profits_when_price_falls():
    b = broker()
    b.submit(Order("BTC/USDT", Side.SELL, 10.0), NOW)
    assert b.cash == pytest.approx(11_000.0)  # proceeds credited

    b.reference_price["BTC/USDT"] = 90.0
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    assert b.cash == pytest.approx(10_100.0)
    assert b.trades[0].net_pnl == pytest.approx(100.0)


def test_positions_close_out_rather_than_stacking():
    b = broker()
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    b.submit(Order("BTC/USDT", Side.SELL, 10.0), NOW)
    assert "BTC/USDT" not in b.get_positions()


def test_scaling_into_a_position_is_refused_rather_than_mis_tracked():
    b = broker()
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    with pytest.raises(InsufficientFunds):
        b.submit(Order("BTC/USDT", Side.BUY, 5.0), NOW)


def test_partial_closes_are_refused():
    b = broker()
    b.submit(Order("BTC/USDT", Side.BUY, 10.0), NOW)
    with pytest.raises(InsufficientFunds):
        b.submit(Order("BTC/USDT", Side.SELL, 4.0), NOW)


def test_an_order_with_no_known_price_does_not_fill():
    b = PaperBroker(starting_cash=1_000.0)
    assert b.submit(Order("ETH/USDT", Side.BUY, 1.0), NOW) is None


def test_starting_cash_must_be_positive():
    with pytest.raises(ValueError):
        PaperBroker(starting_cash=0)
