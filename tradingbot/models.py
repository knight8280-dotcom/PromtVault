"""Core value objects shared by the data, strategy and execution layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utc_from_ms(ms: int) -> datetime:
    """Convert an exchange millisecond timestamp to an aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY

    @property
    def sign(self) -> int:
        """+1 for long exposure, -1 for short exposure."""
        return 1 if self is Side.BUY else -1


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class SignalType(str, Enum):
    """What a strategy wants to happen on the current bar."""

    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT = "exit"
    HOLD = "hold"


@dataclass(frozen=True)
class Candle:
    """A single OHLCV bar. `timestamp` is the bar's open time in UTC."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_ccxt(cls, row: list) -> "Candle":
        ts, o, h, low, c, v = row[:6]
        return cls(utc_from_ms(int(ts)), float(o), float(h), float(low), float(c), float(v))

    def as_row(self) -> list:
        return [
            int(self.timestamp.timestamp() * 1000),
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
        ]


@dataclass(frozen=True)
class Signal:
    """A strategy's intent for one bar, before risk sizing is applied."""

    type: SignalType
    reason: str = ""
    # Optional strategy-supplied stop; the risk manager uses it for position sizing.
    stop_price: float | None = None
    # Fraction of the normal position size, allowing conviction-weighted entries.
    strength: float = 1.0

    @property
    def is_entry(self) -> bool:
        return self.type in (SignalType.ENTER_LONG, SignalType.ENTER_SHORT)

    @property
    def side(self) -> Side | None:
        if self.type is SignalType.ENTER_LONG:
            return Side.BUY
        if self.type is SignalType.ENTER_SHORT:
            return Side.SELL
        return None


HOLD = Signal(SignalType.HOLD)


@dataclass
class Order:
    symbol: str
    side: Side
    amount: float
    type: OrderType = OrderType.MARKET
    price: float | None = None
    client_id: str | None = None
    reduce_only: bool = False


@dataclass
class Fill:
    """The result of an order actually executing."""

    symbol: str
    side: Side
    amount: float
    price: float
    fee: float
    timestamp: datetime
    order_id: str = ""

    @property
    def notional(self) -> float:
        return self.amount * self.price


@dataclass
class Position:
    """An open position. Long positions have a positive amount, shorts negative."""

    symbol: str
    side: Side
    amount: float
    entry_price: float
    opened_at: datetime
    stop_price: float | None = None
    take_profit_price: float | None = None
    fees_paid: float = 0.0

    @property
    def signed_amount(self) -> float:
        return self.amount * self.side.sign

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.entry_price) * self.signed_amount

    def notional(self, price: float) -> float:
        return self.amount * price


@dataclass
class Trade:
    """A completed round trip, recorded for reporting."""

    symbol: str
    side: Side
    amount: float
    entry_price: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    fees: float
    reason: str = ""

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.amount * self.side.sign

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.fees

    @property
    def return_pct(self) -> float:
        cost = self.entry_price * self.amount
        return self.net_pnl / cost if cost else 0.0

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float
    cash: float
    position_value: float = 0.0


@dataclass
class AccountState:
    """Snapshot of the account the risk manager reasons about."""

    cash: float
    equity: float
    positions: dict[str, Position] = field(default_factory=dict)
    peak_equity: float = 0.0
    realized_pnl_today: float = 0.0
