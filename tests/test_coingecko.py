"""The keyless public data source. Network is faked; nothing here calls out."""

import io
import json
import urllib.error

import pytest

from tradingbot.data import coingecko
from tradingbot.data.coingecko import CoinGeckoError, coin_id, fetch_daily, fetch_hourly


def fake_response(payload):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return Response(json.dumps(payload).encode())


@pytest.fixture
def prices(monkeypatch):
    def install(payload):
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda url, timeout=None: fake_response(payload)
        )
    return install


# ------------------------------------------------------------- symbols
@pytest.mark.parametrize(
    "symbol,expected",
    [("BTC/USDT", "bitcoin"), ("ETH", "ethereum"), ("sol/usd", "solana"),
     ("LINK/USD", "chainlink")],
)
def test_known_symbols_map_to_coin_ids(symbol, expected):
    assert coin_id(symbol) == expected


def test_an_unknown_symbol_falls_through_as_a_coin_id():
    assert coin_id("SOMETOKEN/USD") == "sometoken"


# --------------------------------------------------------------- hourly
def test_hourly_prices_become_candles(prices):
    prices({"prices": [[1700000000000, 100.0], [1700003600000, 110.0], [1700007200000, 105.0]]})
    candles = fetch_hourly("BTC/USD", days=30)

    assert len(candles) == 2  # n prices produce n-1 bars
    first = candles[0]
    assert first.open == 100.0 and first.close == 110.0
    assert first.high == 110.0 and first.low == 100.0


def test_bars_span_only_open_to_close(prices):
    """The source has no intrabar data, so the range must never exceed open/close."""
    prices({"prices": [[1700000000000, 100.0], [1700003600000, 90.0], [1700007200000, 95.0]]})
    for candle in fetch_hourly("BTC/USD", days=30):
        assert candle.high == max(candle.open, candle.close)
        assert candle.low == min(candle.open, candle.close)


def test_candles_are_ordered_and_timezone_aware(prices):
    prices({"prices": [[1700000000000 + i * 3600000, 100.0 + i] for i in range(10)]})
    candles = fetch_hourly("BTC/USD", days=30)
    assert all(c.timestamp.tzinfo is not None for c in candles)
    assert [c.timestamp for c in candles] == sorted(c.timestamp for c in candles)


@pytest.mark.parametrize("days", [0, 1, 91, 365])
def test_an_out_of_range_day_count_is_rejected(days):
    """Asking beyond the hourly window silently downgrades upstream, so refuse it."""
    with pytest.raises(CoinGeckoError, match="2 to 90 days"):
        fetch_hourly("BTC/USD", days=days)


def test_an_empty_response_is_reported(prices):
    prices({"prices": []})
    with pytest.raises(CoinGeckoError, match="no price history"):
        fetch_hourly("BTC/USD", days=30)


# ---------------------------------------------------------------- daily
def test_daily_ohlc_is_used_as_given(prices):
    prices([[1700000000000, 100.0, 120.0, 95.0, 110.0]])
    candle = fetch_daily("BTC/USD", days=365)[0]
    # Daily rows are genuine OHLC, so the range is wider than open/close.
    assert candle.high == 120.0 and candle.low == 95.0


def test_an_empty_daily_response_is_reported(prices):
    prices([])
    with pytest.raises(CoinGeckoError, match="no OHLC data"):
        fetch_daily("BTC/USD")


# --------------------------------------------------------------- errors
def test_rate_limiting_is_explained(monkeypatch):
    def boom(url, timeout=None):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(CoinGeckoError, match="rate limit"):
        fetch_hourly("BTC/USD", days=30)


def test_an_unreachable_host_is_reported(monkeypatch):
    def boom(url, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(CoinGeckoError, match="could not reach"):
        fetch_hourly("BTC/USD", days=30)


def test_a_malformed_response_is_reported(monkeypatch):
    class Bad(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=None: Bad(b"not json"))
    with pytest.raises(CoinGeckoError, match="malformed"):
        fetch_hourly("BTC/USD", days=30)


def test_candles_from_this_source_run_through_a_backtest(prices, config):
    """The whole point: this data must be usable by the rest of the bot."""
    import math

    from tradingbot.backtest import Backtester
    from tradingbot.strategies import get_strategy

    series = [[1700000000000 + i * 3600000, 100 + 20 * math.sin(i / 15)] for i in range(600)]
    prices({"prices": series})
    candles = fetch_hourly("BTC/USD", days=30)

    result = Backtester(config, get_strategy("sma_cross", fast_period=10, slow_period=30)).run(
        "BTC/USD", candles
    )
    assert result.metrics.benchmark_return_pct is not None
    assert len(result.equity_curve) == len(candles)
