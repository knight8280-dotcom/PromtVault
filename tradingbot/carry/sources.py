"""Funding rate data.

ccxt is imported lazily, so the carry analysis, its tests, and the whole rest of
the bot work without it installed or any network access.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from .models import DEFAULT_FUNDING_INTERVAL_HOURS, FundingHistory, FundingRate

log = logging.getLogger(__name__)


class FundingSourceError(Exception):
    """The venue could not be reached, or does not offer what was asked for."""


#: Venues with perpetual funding that ccxt exposes uniformly.
PERP_VENUES = ["binance", "bybit", "okx", "kucoinfutures", "gate", "bitget"]


class FundingSource(ABC):
    """Read-only access to one venue's funding data."""

    @abstractmethod
    def current(self, symbol: str) -> FundingRate: ...

    @abstractmethod
    def history(self, symbol: str, limit: int = 30) -> FundingHistory: ...

    @abstractmethod
    def perpetual_symbols(self) -> list[str]: ...

    def close(self) -> None:
        """Release network resources."""


def _load_ccxt():
    try:
        import ccxt  # noqa: PLC0415 - deliberately lazy
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise FundingSourceError(
            "ccxt is required to read funding rates: pip install ccxt"
        ) from exc
    return ccxt


class CcxtFundingSource(FundingSource):
    """Funding rates via ccxt's unified swap API."""

    def __init__(self, venue: str = "binance", timeout: int = 20_000) -> None:
        ccxt = _load_ccxt()
        if not hasattr(ccxt, venue):
            raise FundingSourceError(f"ccxt does not support venue {venue!r}")

        self.venue = venue
        self.client = getattr(ccxt, venue)(
            {"enableRateLimit": True, "timeout": timeout, "options": {"defaultType": "swap"}}
        )

    # ------------------------------------------------------------------
    def current(self, symbol: str) -> FundingRate:
        try:
            raw = self.client.fetch_funding_rate(symbol)
        except Exception as exc:  # noqa: BLE001 - ccxt raises assorted types
            raise FundingSourceError(f"{self.venue}: could not read funding for {symbol}: {exc}") from exc
        return self._to_rate(symbol, raw)

    def history(self, symbol: str, limit: int = 30) -> FundingHistory:
        try:
            rows = self.client.fetch_funding_rate_history(symbol, limit=limit)
        except Exception as exc:  # noqa: BLE001
            raise FundingSourceError(
                f"{self.venue}: could not read funding history for {symbol}: {exc}"
            ) from exc

        rates = [self._to_rate(symbol, row) for row in rows]
        rates.sort(key=lambda r: r.timestamp)
        return FundingHistory(symbol=symbol, venue=self.venue, rates=rates)

    def perpetual_symbols(self) -> list[str]:
        try:
            markets = self.client.load_markets()
        except Exception as exc:  # noqa: BLE001
            raise FundingSourceError(f"{self.venue}: could not list markets: {exc}") from exc

        return sorted(
            symbol for symbol, market in markets.items()
            if market.get("swap") and market.get("active") and market.get("linear")
        )

    # ------------------------------------------------------------------
    def _to_rate(self, symbol: str, raw: dict) -> FundingRate:
        rate = raw.get("fundingRate")
        if rate is None:
            raise FundingSourceError(f"{self.venue}: no funding rate in response for {symbol}")

        timestamp = raw.get("timestamp") or raw.get("fundingTimestamp")
        when = (
            datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            if timestamp else datetime.now(timezone.utc)
        )
        next_ts = raw.get("nextFundingTimestamp")
        next_funding = (
            datetime.fromtimestamp(next_ts / 1000, tz=timezone.utc) if next_ts else None
        )

        return FundingRate(
            symbol=symbol,
            venue=self.venue,
            rate=float(rate),
            timestamp=when,
            interval_hours=self._interval_hours(raw),
            next_funding=next_funding,
            mark_price=_maybe_float(raw.get("markPrice")),
            index_price=_maybe_float(raw.get("indexPrice")),
        )

    def _interval_hours(self, raw: dict) -> float:
        """Read the settlement interval rather than assuming eight hours.

        Getting this wrong scales every APR in the report by 2x or 8x, so it is
        taken from the venue whenever the venue says.
        """
        interval = raw.get("interval") or raw.get("fundingInterval")
        if isinstance(interval, str) and interval.endswith("h"):
            try:
                return float(interval[:-1])
            except ValueError:
                pass
        if isinstance(interval, (int, float)) and interval > 0:
            return float(interval)
        return DEFAULT_FUNDING_INTERVAL_HOURS

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                log.debug("ignoring error closing funding client", exc_info=True)


def _maybe_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
