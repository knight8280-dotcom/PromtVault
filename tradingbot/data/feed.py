"""Getting candles from wherever they live: cache, exchange, or a generator."""

from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import Candle
from . import csv_store

log = logging.getLogger(__name__)

TIMEFRAME_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
}


def timeframe_delta(timeframe: str) -> timedelta:
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"unsupported timeframe {timeframe!r}")
    return timedelta(minutes=TIMEFRAME_MINUTES[timeframe])


def load_history(
    symbol: str,
    timeframe: str,
    *,
    data_dir: str = "data_cache",
    csv_path: str | None = None,
    exchange_config=None,
    days: int = 365,
    refresh: bool = False,
) -> list[Candle]:
    """Load candles, preferring an explicit CSV, then the cache, then the exchange."""
    if csv_path:
        return csv_store.load(csv_path)

    cached_at = csv_store.cache_path(data_dir, symbol, timeframe)
    if cached_at.exists() and not refresh:
        candles = csv_store.load(cached_at)
        log.info("loaded %d cached candles for %s %s", len(candles), symbol, timeframe)
        return candles

    if exchange_config is None:
        raise FileNotFoundError(
            f"no cached data for {symbol} {timeframe} at {cached_at}. Either pass "
            f"--csv, run `tradingbot fetch` to download it, or use `--synthetic` "
            f"to try the engine on generated data."
        )

    return download(symbol, timeframe, exchange_config, days=days, data_dir=data_dir)


def download(
    symbol: str,
    timeframe: str,
    exchange_config,
    *,
    days: int = 365,
    data_dir: str = "data_cache",
) -> list[Candle]:
    """Download history from the exchange and write it to the cache."""
    from ..exchange.ccxt_adapter import CcxtBroker

    broker = CcxtBroker(exchange_config, allow_trading=False)
    try:
        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
        log.info("downloading %s %s (%d days) from %s", symbol, timeframe, days, exchange_config.name)
        fresh = broker.fetch_history(symbol, timeframe, since)
    finally:
        broker.close()

    path = csv_store.cache_path(data_dir, symbol, timeframe)
    existing = csv_store.load(path) if Path(path).exists() else []
    merged = csv_store.merge(existing, fresh)
    csv_store.save(path, merged)
    log.info("cached %d candles at %s", len(merged), path)
    return merged


def generate_synthetic(
    *,
    bars: int = 2000,
    start_price: float = 30_000.0,
    timeframe: str = "1h",
    volatility: float = 0.012,
    drift: float = 0.0002,
    trend_strength: float = 0.6,
    seed: int = 7,
    start: datetime | None = None,
) -> list[Candle]:
    """Generate plausible OHLCV data for demos and tests.

    This is a geometric random walk with slow regime shifts, so it trends often
    enough to exercise the strategies. It is emphatically NOT market data — never
    judge a strategy on it.
    """
    rng = random.Random(seed)
    delta = timeframe_delta(timeframe)
    ts = start or datetime.now(timezone.utc) - delta * bars
    price = start_price
    regime = 1.0
    out: list[Candle] = []

    for i in range(bars):
        # Occasionally flip the prevailing trend so both regimes get tested.
        if i % 180 == 0:
            regime = rng.choice([1.0, -1.0, 0.2])
        shock = rng.gauss(drift * regime * trend_strength, volatility)
        open_ = price
        close = max(price * math.exp(shock), 0.01)
        spread = abs(close - open_) + price * volatility * rng.random() * 0.5
        high = max(open_, close) + spread * rng.random()
        low = max(min(open_, close) - spread * rng.random(), 0.01)
        volume = abs(rng.gauss(1000, 300)) + abs(shock) * 50_000

        out.append(Candle(ts, open_, high, low, close, volume))
        price = close
        ts += delta

    return out
