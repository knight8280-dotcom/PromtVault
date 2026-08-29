"""A broker that simulates fills locally against real market data.

Used both by the backtester and by paper-trading mode. Fills model fees and
slippage so paper results are not systematically optimistic, and cash is tracked
so the bot cannot spend money it does not have.
"""

from __future__ import annotations

from datetime import datetime

from ..models import Candle, Fill, Order, OrderType, Position, Side, Trade
from .base import Broker


class InsufficientFunds(Exception):
    """Raised when an order would overdraw the simulated account."""


class PaperBroker(Broker):
    """Simulated execution with explicit fee and slippage modelling."""

    def __init__(
        self,
        starting_cash: float,
        fee_rate: float = 0.001,
        slippage_pct: float = 0.0005,
        data_source: Broker | None = None,
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        # Optional real broker used purely for market data in paper mode.
        self.data_source = data_source

        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.fills: list[Fill] = []
        self._marks: dict[str, float] = {}
        self._order_seq = 0
        # Set by the backtester so simulated fills use the bar being replayed.
        self.reference_price: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Broker interface
    # ------------------------------------------------------------------
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        if self.data_source is None:
            raise RuntimeError("PaperBroker has no data source; pass data_source= to fetch candles")
        return self.data_source.fetch_candles(symbol, timeframe, limit)

    def get_positions(self) -> dict[str, Position]:
        return self.positions

    def get_cash(self) -> float:
        return self.cash

    def last_price(self, symbol: str) -> float | None:
        return self._marks.get(symbol)

    def mark(self, symbol: str, price: float) -> None:
        """Record the latest price, used for equity marking and default fills."""
        self._marks[symbol] = price
        self.reference_price[symbol] = price

    def get_equity(self, marks: dict[str, float] | None = None) -> float:
        marks = {**self._marks, **(marks or {})}
        equity = self.cash
        for symbol, position in self.positions.items():
            price = marks.get(symbol, position.entry_price)
            if position.side is Side.BUY:
                # Long positions were paid for in cash; add back their market value.
                equity += position.notional(price)
            else:
                # Short proceeds are already in cash; add the mark-to-market P&L.
                equity += position.unrealized_pnl(price)
        return equity

    def submit(self, order: Order, timestamp: datetime) -> Fill | None:
        price = self._fill_price(order)
        if price is None or price <= 0:
            return None

        fee = price * order.amount * self.fee_rate
        self._order_seq += 1
        fill = Fill(
            symbol=order.symbol,
            side=order.side,
            amount=order.amount,
            price=price,
            fee=fee,
            timestamp=timestamp,
            order_id=f"paper-{self._order_seq}",
        )

        existing = self.positions.get(order.symbol)
        if existing is not None and existing.side is not order.side:
            self._close(existing, fill, order)
        elif existing is not None:
            raise InsufficientFunds(
                f"already holding {order.symbol}; scaling into a position is not supported"
            )
        else:
            self._open(fill, order)

        self.fills.append(fill)
        self._marks[order.symbol] = price
        return fill

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _fill_price(self, order: Order) -> float | None:
        base = order.price if order.type is OrderType.LIMIT and order.price else None
        if base is None:
            base = self.reference_price.get(order.symbol) or self._marks.get(order.symbol)
        if base is None:
            return None
        # Slippage always works against us, on both entries and exits.
        return base * (1 + self.slippage_pct * order.side.sign)

    def _open(self, fill: Fill, order: Order) -> None:
        cost = fill.notional + fill.fee
        if fill.side is Side.BUY:
            if cost > self.cash + 1e-9:
                raise InsufficientFunds(
                    f"need {cost:,.2f} to open {order.symbol} but only {self.cash:,.2f} available"
                )
            self.cash -= cost
        else:
            # Shorting credits the proceeds and debits the fee.
            self.cash += fill.notional - fill.fee

        self.positions[order.symbol] = Position(
            symbol=order.symbol,
            side=fill.side,
            amount=fill.amount,
            entry_price=fill.price,
            opened_at=fill.timestamp,
            fees_paid=fill.fee,
        )

    def _close(self, position: Position, fill: Fill, order: Order) -> None:
        if abs(fill.amount - position.amount) > 1e-9:
            raise InsufficientFunds(
                f"partial closes are not supported: tried to close {fill.amount} of {position.amount}"
            )

        if position.side is Side.BUY:
            self.cash += fill.notional - fill.fee
        else:
            # Buying back a short costs the notional plus the fee.
            self.cash -= fill.notional + fill.fee

        self.trades.append(
            Trade(
                symbol=position.symbol,
                side=position.side,
                amount=position.amount,
                entry_price=position.entry_price,
                exit_price=fill.price,
                opened_at=position.opened_at,
                closed_at=fill.timestamp,
                fees=position.fees_paid + fill.fee,
                reason=order.client_id or "",
            )
        )
        del self.positions[order.symbol]
