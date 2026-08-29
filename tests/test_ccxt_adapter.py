"""The live-exchange path. Exercised against a fake ccxt, never a real venue."""

from datetime import datetime, timezone

import pytest

from tradingbot.config import ExchangeConfig
from tradingbot.models import Order, OrderType, Side

from . import fake_ccxt

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def candles(count=5, start_ms=1_700_000_000_000, step_ms=3_600_000):
    return [
        [start_ms + i * step_ms, 100 + i, 101 + i, 99 + i, 100.5 + i, 10.0]
        for i in range(count)
    ]


def broker(monkeypatch, *, allow_trading=False, testnet=True, **attrs):
    fake_ccxt.install(monkeypatch, **attrs)
    from tradingbot.exchange.ccxt_adapter import CcxtBroker

    config = ExchangeConfig(name="binance", testnet=testnet)
    return CcxtBroker(config, allow_trading=allow_trading)


# ------------------------------------------------------------ construction
def test_an_unsupported_exchange_is_rejected(monkeypatch):
    fake_ccxt.install(monkeypatch)
    from tradingbot.exchange.ccxt_adapter import CcxtBroker, ExchangeError

    with pytest.raises(ExchangeError, match="does not support"):
        CcxtBroker(ExchangeConfig(name="not_a_real_exchange"))


def test_the_sandbox_is_enabled_when_testnet_is_configured(monkeypatch):
    b = broker(monkeypatch, testnet=True)
    assert b.client.sandbox is True


def test_an_exchange_without_a_sandbox_is_reported_clearly(monkeypatch):
    fake_ccxt.install(monkeypatch, sandbox_supported=False)
    from tradingbot.exchange.ccxt_adapter import CcxtBroker, ExchangeError

    with pytest.raises(ExchangeError, match="sandbox"):
        CcxtBroker(ExchangeConfig(name="binance", testnet=True))


def test_trading_without_credentials_is_refused(monkeypatch):
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("EXCHANGE_API_SECRET", raising=False)
    fake_ccxt.install(monkeypatch)
    from tradingbot.exchange.ccxt_adapter import CcxtBroker, ExchangeError

    with pytest.raises(ExchangeError, match="credentials"):
        CcxtBroker(ExchangeConfig(name="binance"), allow_trading=True)


def test_credentials_are_passed_to_the_client_when_trading(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "key-123")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "secret-456")
    b = broker(monkeypatch, allow_trading=True)
    assert b.client.options["apiKey"] == "key-123"
    assert b.client.options["secret"] == "secret-456"


def test_a_data_only_broker_carries_no_credentials(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "key-123")
    b = broker(monkeypatch, allow_trading=False)
    assert "apiKey" not in b.client.options


# -------------------------------------------------------------- market data
def test_the_still_forming_final_bar_is_dropped(monkeypatch):
    """A strategy must never see the bar that is still printing."""
    rows = candles(5)
    b = broker(monkeypatch, ohlcv=rows)
    fetched = b.fetch_candles("BTC/USDT", "1h", 5)
    assert len(fetched) == 4
    assert fetched[-1].close == rows[-2][4]


def test_fetching_with_no_data_returns_empty(monkeypatch):
    b = broker(monkeypatch, ohlcv=[])
    assert b.fetch_candles("BTC/USDT", "1h", 10) == []


def test_candles_are_converted_with_utc_timestamps(monkeypatch):
    b = broker(monkeypatch, ohlcv=candles(3))
    candle = b.fetch_candles("BTC/USDT", "1h", 3)[0]
    assert candle.timestamp.tzinfo is timezone.utc
    assert candle.open == 100


def test_history_pages_forward_through_time(monkeypatch):
    rows = candles(50)
    b = broker(monkeypatch, ohlcv=rows)
    history = b.fetch_history("BTC/USDT", "1h", rows[0][0], rows[-1][0])
    assert len(history) == len(rows) - 1  # bounded by `until`
    assert history[0].timestamp < history[-1].timestamp


def test_history_stops_rather_than_looping_forever(monkeypatch):
    # One row that never advances the cursor would spin an unguarded loop.
    b = broker(monkeypatch, ohlcv=candles(1))
    history = b.fetch_history("BTC/USDT", "1h", 0, 9_999_999_999_999)
    assert len(history) <= 1


def test_last_price_reads_the_ticker(monkeypatch):
    b = broker(monkeypatch, ticker={"last": 42_000.0})
    assert b.last_price("BTC/USDT") == 42_000.0


def test_last_price_returns_none_when_the_ticker_fails(monkeypatch):
    b = broker(monkeypatch, failures=[fake_ccxt.NetworkError("down")] * 5)
    monkeypatch.setattr("tradingbot.exchange.ccxt_adapter.time.sleep", lambda _: None)
    assert b.last_price("BTC/USDT") is None


# ------------------------------------------------------------------ account
def test_cash_is_read_from_the_free_balance(monkeypatch):
    b = broker(monkeypatch, balance={"free": {"USDT": 1_234.0}})
    assert b.get_cash("USDT") == 1_234.0


def test_a_missing_balance_currency_reads_as_zero(monkeypatch):
    b = broker(monkeypatch, balance={"free": {}})
    assert b.get_cash("USDT") == 0.0


# ---------------------------------------------------------------- execution
def test_a_data_only_broker_refuses_to_submit(monkeypatch):
    from tradingbot.exchange.ccxt_adapter import ExchangeError

    b = broker(monkeypatch, allow_trading=False)
    with pytest.raises(ExchangeError, match="data-only"):
        b.submit(Order("BTC/USDT", Side.BUY, 1.0), NOW)


def test_a_market_order_fills_and_opens_a_position(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    b = broker(monkeypatch, allow_trading=True, ticker={"last": 100.0})

    fill = b.submit(Order("BTC/USDT", Side.BUY, 2.0), NOW)
    assert fill is not None
    assert fill.amount == pytest.approx(2.0)
    assert fill.price == pytest.approx(100.0)
    assert "BTC/USDT" in b.get_positions()
    assert ("create_order", "BTC/USDT", "market", "buy", 2.0, None) in b.client.calls


def test_a_limit_order_passes_its_price_through(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    b = broker(monkeypatch, allow_trading=True)

    b.submit(Order("BTC/USDT", Side.BUY, 1.0, type=OrderType.LIMIT, price=95.0), NOW)
    call = next(c for c in b.client.calls if c[0] == "create_order")
    assert call[2] == "limit" and call[5] == pytest.approx(95.0)


def test_a_limit_order_without_a_price_is_refused(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    from tradingbot.exchange.ccxt_adapter import ExchangeError

    b = broker(monkeypatch, allow_trading=True)
    with pytest.raises(ExchangeError, match="require a price"):
        b.submit(Order("BTC/USDT", Side.BUY, 1.0, type=OrderType.LIMIT), NOW)


def test_an_unfilled_order_reports_no_fill(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    b = broker(
        monkeypatch, allow_trading=True,
        order_response={"id": "x", "filled": 0.0, "status": "canceled"},
    )
    assert b.submit(Order("BTC/USDT", Side.BUY, 1.0), NOW) is None
    assert "BTC/USDT" not in b.get_positions()


def test_an_amount_rounding_to_zero_is_not_sent(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    b = broker(monkeypatch, allow_trading=True)
    assert b.submit(Order("BTC/USDT", Side.BUY, 1e-12), NOW) is None
    assert not [c for c in b.client.calls if c[0] == "create_order"]


def test_a_partial_fill_records_the_filled_amount(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    b = broker(
        monkeypatch, allow_trading=True,
        order_response={"id": "p", "filled": 0.4, "average": 100.0,
                        "fee": {"cost": 0.04}, "timestamp": 1_700_000_000_000},
    )
    fill = b.submit(Order("BTC/USDT", Side.BUY, 1.0), NOW)
    # The position must reflect what actually filled, not what was requested.
    assert fill.amount == pytest.approx(0.4)
    assert b.get_positions()["BTC/USDT"].amount == pytest.approx(0.4)


def test_an_opposing_fill_closes_the_position(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    b = broker(monkeypatch, allow_trading=True)
    b.submit(Order("BTC/USDT", Side.BUY, 1.0), NOW)
    b.submit(Order("BTC/USDT", Side.SELL, 1.0), NOW)
    assert "BTC/USDT" not in b.get_positions()


def test_positions_can_be_adopted_after_a_restart(monkeypatch):
    from tradingbot.models import Position

    b = broker(monkeypatch)
    saved = {"BTC/USDT": Position("BTC/USDT", Side.BUY, 1.0, 100.0, NOW)}
    b.adopt_positions(saved)
    assert b.get_positions()["BTC/USDT"].entry_price == 100.0


# -------------------------------------------------------------------- retry
def test_a_transient_network_error_is_retried(monkeypatch):
    b = broker(
        monkeypatch, ohlcv=candles(3),
        failures=[fake_ccxt.NetworkError("blip")],
    )
    b.max_retries = 3
    monkeypatch.setattr("tradingbot.exchange.ccxt_adapter.time.sleep", lambda _: None)
    assert len(b.fetch_candles("BTC/USDT", "1h", 3)) == 2  # recovered on retry


def test_retries_give_up_and_raise_after_the_limit(monkeypatch):
    from tradingbot.exchange.ccxt_adapter import ExchangeError

    b = broker(monkeypatch, failures=[fake_ccxt.RequestTimeout("slow")] * 10)
    b.max_retries = 2
    monkeypatch.setattr("tradingbot.exchange.ccxt_adapter.time.sleep", lambda _: None)
    with pytest.raises(ExchangeError, match="after 2 attempts"):
        b.fetch_candles("BTC/USDT", "1h", 3)


def test_a_non_transient_error_is_not_retried(monkeypatch):
    from tradingbot.exchange.ccxt_adapter import ExchangeError

    b = broker(monkeypatch, failures=[fake_ccxt.BaseError("bad symbol")] * 5)
    b.max_retries = 5
    with pytest.raises(ExchangeError, match="bad symbol"):
        b.fetch_candles("BTC/USDT", "1h", 3)
    # A rejected request must fail immediately rather than hammering the venue.
    assert len([c for c in b.client.calls if c[0] == "fetch_ohlcv"]) == 0


def test_closing_the_broker_closes_the_client(monkeypatch):
    b = broker(monkeypatch)
    b.close()
    assert ("close",) in b.client.calls
