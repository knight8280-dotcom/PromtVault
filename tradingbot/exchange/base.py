"""The broker interface the engine talks to.

Backtests, paper trading and live trading all go through this one interface, so
the engine cannot tell them apart — which is the whole point: the code path that
was backtested is the code path that trades.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import Candle, Fill, Order, Position


class Broker(ABC):
    """Executes orders and reports account state."""

    @abstractmethod
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        """Return the most recent closed candles, oldest first."""

    @abstractmethod
    def submit(self, order: Order, timestamp: datetime) -> Fill | None:
        """Execute an order. Returns the fill, or None if it did not execute."""

    @abstractmethod
    def get_positions(self) -> dict[str, Position]:
        """Currently open positions, keyed by symbol."""

    @abstractmethod
    def get_cash(self) -> float:
        """Free quote-currency balance."""

    @abstractmethod
    def get_equity(self, marks: dict[str, float] | None = None) -> float:
        """Cash plus the marked value of open positions."""

    def last_price(self, symbol: str) -> float | None:
        """Best known price for a symbol, used for marking positions."""
        return None

    def close(self) -> None:
        """Release any network resources."""
