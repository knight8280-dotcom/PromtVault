"""Live exchange access via ccxt.

ccxt is imported lazily so the rest of the bot — backtesting, paper trading and
the whole test suite — works without it installed or any network access.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from ..config import ExchangeConfig
from ..models import Candle, Fill, Order, OrderType, Position, Side
from .base import Broker

log = logging.getLogger(__name__)


class ExchangeError(Exception):
    """Raised when the exchange rejects a request or cannot be reached."""


def _load_ccxt():
    try:
        import ccxt  # noqa: PLC0415 - deliberately lazy
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ExchangeError(
            "ccxt is required for live data and trading: pip install ccxt"
        ) from exc
    return ccxt


class CcxtBroker(Broker):
    """Reads market data and (optionally) places real orders through ccxt."""

    def __init__(
        self,
        config: ExchangeConfig,
        *,
        allow_trading: bool = False,
        max_retries: int = 3,
    ) -> None:
        ccxt = _load_ccxt()
        if not hasattr(ccxt, config.name):
            raise ExchangeError(f"ccxt does not support exchange {config.name!r}")

        self.config = config
        self.allow_trading = allow_trading
        self.max_retries = max_retries

        options: dict = {"enableRateLimit": config.rate_limit}
        if allow_trading:
            creds = config.credentials()
            if not creds.get("apiKey") or not creds.get("secret"):
                raise ExchangeError(
                    f"live trading needs credentials in ${config.api_key_env} and "
                    f"${config.api_secret_env}, but they are not set"
                )
            options.update(creds)

        self.client = getattr(ccxt, config.name)(options)
        if config.testnet:
            self._enable_testnet()

        self._positions: dict[str, Position] = {}

    def _enable_testnet(self) -> None:
        try:
            self.client.set_sandbox_mode(True)
            log.info("exchange %s running against its testnet/sandbox", self.config.name)
        except Exception as exc:  # noqa: BLE001 - ccxt raises assorted types
            raise ExchangeError(
                f"{self.config.name} does not offer a sandbox; set exchange.testnet=false "
                f"to trade against production ({exc})"
            ) from exc

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        rows = self._retry(self.client.fetch_ohlcv, symbol, timeframe, None, limit)
        candles = [Candle.from_ccxt(row) for row in rows]
        # The final bar is still forming; strategies must only see closed bars.
        return candles[:-1] if candles else candles

    def fetch_history(
        self, symbol: str, timeframe: str, since_ms: int, until_ms: int | None = None
    ) -> list[Candle]:
        """Page backwards through history until `until_ms` (or now) is reached."""
        out: list[Candle] = []
        cursor = since_ms
        until = until_ms or int(time.time() * 1000)
        while cursor < until:
            rows = self._retry(self.client.fetch_ohlcv, symbol, timeframe, cursor, 1000)
            if not rows:
                break
            batch = [Candle.from_ccxt(row) for row in rows]
            out.extend(c for c in batch if c.timestamp.timestamp() * 1000 < until)
            next_cursor = int(rows[-1][0]) + 1
            if next_cursor <= cursor:  # exchange stopped advancing; avoid looping forever
                break
            cursor = next_cursor
            if len(rows) < 2:
                break
        return out

    def last_price(self, symbol: str) -> float | None:
        try:
            ticker = self._retry(self.client.fetch_ticker, symbol)
        except ExchangeError:
            return None
        price = ticker.get("last") or ticker.get("close")
        return float(price) if price else None

    # ------------------------------------------------------------------
    # Account and execution
    # ------------------------------------------------------------------
    def get_cash(self, quote: str = "USDT") -> float:
        balance = self._retry(self.client.fetch_balance)
        free = balance.get("free", {})
        return float(free.get(quote, 0.0))

    def get_positions(self) -> dict[str, Position]:
        return self._positions

    def get_equity(self, marks: dict[str, float] | None = None) -> float:
        marks = marks or {}
        equity = self.get_cash()
        for symbol, position in self._positions.items():
            price = marks.get(symbol) or self.last_price(symbol) or position.entry_price
            equity += position.notional(price) if position.side is Side.BUY else position.unrealized_pnl(price)
        return equity

    def submit(self, order: Order, timestamp: datetime) -> Fill | None:
        if not self.allow_trading:
            raise ExchangeError("this broker is data-only; live trading was not enabled")

        amount = float(self.client.amount_to_precision(order.symbol, order.amount))
        if amount <= 0:
            log.warning("order for %s rounded to zero at exchange precision", order.symbol)
            return None

        if order.type is OrderType.LIMIT:
            if order.price is None:
                raise ExchangeError("limit orders require a price")
            price = float(self.client.price_to_precision(order.symbol, order.price))
            raw = self._retry(
                self.client.create_order, order.symbol, "limit", order.side.value, amount, price
            )
        else:
            raw = self._retry(
                self.client.create_order, order.symbol, "market", order.side.value, amount
            )

        return self._to_fill(raw, order, timestamp)

    def _to_fill(self, raw: dict, order: Order, timestamp: datetime) -> Fill | None:
        filled = float(raw.get("filled") or 0.0)
        if filled <= 0:
            log.warning("order %s returned no fill: %s", raw.get("id"), raw.get("status"))
            return None

        price = float(raw.get("average") or raw.get("price") or 0.0)
        if price <= 0:
            price = self.last_price(order.symbol) or 0.0
        fee_info = raw.get("fee") or {}
        fee = float(fee_info.get("cost") or 0.0)

        ts = raw.get("timestamp")
        when = datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts else timestamp

        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            amount=filled,
            price=price,
            fee=fee,
            timestamp=when,
            order_id=str(raw.get("id", "")),
        )
        self._apply_fill(fill)
        return fill

    def _apply_fill(self, fill: Fill) -> None:
        """Mirror the exchange fill into local position bookkeeping."""
        existing = self._positions.get(fill.symbol)
        if existing is not None and existing.side is not fill.side:
            del self._positions[fill.symbol]
            return
        self._positions[fill.symbol] = Position(
            symbol=fill.symbol,
            side=fill.side,
            amount=fill.amount,
            entry_price=fill.price,
            opened_at=fill.timestamp,
            fees_paid=fill.fee,
        )

    def adopt_positions(self, positions: dict[str, Position]) -> None:
        """Restore positions recovered from saved state after a restart."""
        self._positions = dict(positions)

    # ------------------------------------------------------------------
    def _retry(self, fn, *args):
        """Call a ccxt method, retrying transient network errors with backoff."""
        ccxt = _load_ccxt()
        transient = (ccxt.NetworkError, ccxt.RequestTimeout, ccxt.ExchangeNotAvailable)
        delay = 2.0
        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn(*args)
            except transient as exc:
                last = exc
                if attempt == self.max_retries:
                    break
                log.warning("%s failed (%s); retrying in %.0fs", fn.__name__, exc, delay)
                time.sleep(delay)
                delay *= 2
            except ccxt.BaseError as exc:
                raise ExchangeError(f"{fn.__name__} failed: {exc}") from exc
        raise ExchangeError(f"{fn.__name__} failed after {self.max_retries} attempts: {last}")

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - closing must never mask a real error
                log.debug("ignoring error while closing exchange client", exc_info=True)
