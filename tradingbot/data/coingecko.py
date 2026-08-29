"""Public market data with no API key required.

Exchange APIs are the better source — real OHLC, real volume — but they need
ccxt, and they are geo-blocked from many datacenters. This gets you real price
history anywhere, so the validation tools are usable without an exchange account.

The limitation is stated plainly because it changes results: the free endpoint
returns closing prices only, so bars carry no true intrabar high or low. Stops
and targets can only be evaluated against the close, which makes them trigger
LESS often than they would in reality. Treat stop-heavy results from this source
as optimistic and confirm on exchange data before trusting them.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone

from ..models import Candle

log = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"

#: Symbols mapped to CoinGecko's coin ids. Anything else can be passed directly.
COIN_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "LINK": "chainlink",
    "ADA": "cardano", "AVAX": "avalanche-2", "DOT": "polkadot", "MATIC": "matic-network",
    "POL": "polygon-ecosystem-token", "DOGE": "dogecoin", "XRP": "ripple",
    "LTC": "litecoin", "UNI": "uniswap", "ATOM": "cosmos", "NEAR": "near",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism", "BNB": "binancecoin",
}


class CoinGeckoError(Exception):
    """The public data source could not answer."""


def coin_id(symbol: str) -> str:
    """Resolve BASE/QUOTE or a bare base symbol to a CoinGecko coin id."""
    base = symbol.split("/")[0].strip().upper()
    return COIN_IDS.get(base, base.lower())


def fetch_hourly(symbol: str, days: int = 90, timeout: float = 40.0) -> list[Candle]:
    """Fetch hourly price history.

    CoinGecko returns hourly points for a 2–90 day range on the free tier; asking
    for more silently downgrades to daily, so `days` is capped rather than
    quietly returning data at a granularity you did not ask for.
    """
    if not 2 <= days <= 90:
        raise CoinGeckoError(
            f"hourly data is available for 2 to 90 days on the free tier, got {days}. "
            f"Use an exchange via `fetch` for longer history."
        )

    url = f"{BASE_URL}/coins/{coin_id(symbol)}/market_chart?vs_currency=usd&days={days}"
    prices = _get(url).get("prices") or []
    if len(prices) < 2:
        raise CoinGeckoError(f"no price history returned for {symbol}")

    # Close-only source: each bar spans the previous close to this one. The range
    # is therefore open-to-close, never wider, which understates real volatility.
    out: list[Candle] = []
    for i in range(1, len(prices)):
        timestamp, close = prices[i]
        previous = prices[i - 1][1]
        out.append(
            Candle(
                timestamp=datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
                open=float(previous),
                high=float(max(previous, close)),
                low=float(min(previous, close)),
                close=float(close),
                volume=0.0,
            )
        )
    log.info("fetched %d hourly bars for %s from CoinGecko", len(out), symbol)
    return out


def fetch_daily(symbol: str, days: int = 365, timeout: float = 40.0) -> list[Candle]:
    """Fetch daily OHLC. Genuine open/high/low/close, but far fewer bars."""
    url = f"{BASE_URL}/coins/{coin_id(symbol)}/ohlc?vs_currency=usd&days={days}"
    rows = _get(url)
    if not isinstance(rows, list) or not rows:
        raise CoinGeckoError(f"no OHLC data returned for {symbol}")

    return [
        Candle(
            timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
            open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]),
            volume=0.0,
        )
        for row in rows
    ]


def _get(url: str, timeout: float = 40.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise CoinGeckoError(
                "CoinGecko rate limit reached (the free tier allows a few calls per "
                "minute). Wait a moment and retry."
            ) from exc
        raise CoinGeckoError(f"CoinGecko returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CoinGeckoError(f"could not reach CoinGecko: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CoinGeckoError("CoinGecko returned a malformed response") from exc
