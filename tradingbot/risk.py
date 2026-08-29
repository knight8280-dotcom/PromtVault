"""Position sizing and the circuit breakers that stop the bot losing money.

The risk manager is deliberately the only place allowed to decide *how much* to
trade. A strategy says "I want to be long"; this decides whether that is
permitted and at what size, or refuses outright.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .config import RiskConfig
from .models import AccountState, Position, Side, Signal


@dataclass
class SizingDecision:
    """The outcome of asking the risk manager to size a trade."""

    amount: float
    stop_price: float | None
    take_profit_price: float | None
    reason: str = ""

    @property
    def approved(self) -> bool:
        return self.amount > 0


REJECTED = SizingDecision(0.0, None, None)


class RiskManager:
    """Enforces per-trade sizing plus account-level circuit breakers."""

    def __init__(self, config: RiskConfig, min_order_notional: float = 0.0) -> None:
        self.config = config
        self.min_order_notional = min_order_notional
        self._halted_reason: str | None = None
        self._day: date | None = None
        self._realized_today: float = 0.0
        self._peak_equity: float = 0.0

    # ------------------------------------------------------------------
    # Account bookkeeping
    # ------------------------------------------------------------------
    def observe_equity(self, equity: float, now: datetime) -> None:
        """Update peak equity and roll the daily loss counter at UTC midnight."""
        if self._day is None:
            self._day = now.date()
        elif now.date() != self._day:
            self._day = now.date()
            self._realized_today = 0.0
            # A new day clears a daily-loss halt but never a drawdown halt.
            if self._halted_reason and self._halted_reason.startswith("daily loss"):
                self._halted_reason = None

        self._peak_equity = max(self._peak_equity, equity)

        if self._peak_equity > 0:
            drawdown = (self._peak_equity - equity) / self._peak_equity
            if drawdown >= self.config.max_drawdown_pct and not self.is_halted:
                self._halted_reason = (
                    f"max drawdown breached: {drawdown:.2%} from peak "
                    f"{self._peak_equity:,.2f} (limit {self.config.max_drawdown_pct:.2%})"
                )

    def record_realized_pnl(self, pnl: float, equity: float) -> None:
        """Record a closed trade's P&L and halt if the daily loss limit is hit."""
        self._realized_today += pnl
        limit = -abs(equity * self.config.max_daily_loss_pct)
        if self._realized_today <= limit and not self.is_halted:
            self._halted_reason = (
                f"daily loss limit hit: {self._realized_today:,.2f} "
                f"(limit {limit:,.2f})"
            )

    @property
    def is_halted(self) -> bool:
        return self._halted_reason is not None

    @property
    def halt_reason(self) -> str | None:
        return self._halted_reason

    @property
    def realized_today(self) -> float:
        return self._realized_today

    @property
    def peak_equity(self) -> float:
        return self._peak_equity

    def restore(
        self,
        *,
        peak_equity: float = 0.0,
        realized_today: float = 0.0,
        halted_reason: str | None = None,
    ) -> None:
        """Reinstate counters saved before a restart, so limits survive a crash."""
        self._peak_equity = peak_equity
        self._realized_today = realized_today
        self._halted_reason = halted_reason

    def resume(self) -> None:
        """Clear a halt. Only ever called on explicit operator instruction."""
        self._halted_reason = None

    # ------------------------------------------------------------------
    # Sizing
    # ------------------------------------------------------------------
    def size_entry(
        self,
        signal: Signal,
        price: float,
        account: AccountState,
        symbol: str,
    ) -> SizingDecision:
        """Decide how large an entry may be, or reject it with a reason."""
        if self.is_halted:
            return self._reject(f"trading halted: {self._halted_reason}")
        if price <= 0:
            return self._reject("invalid price")

        side = signal.side
        if side is None:
            return self._reject("signal is not an entry")
        if side is Side.SELL and not self.config.allow_shorts:
            return self._reject("short selling is disabled in risk config")
        if symbol in account.positions:
            return self._reject(f"already holding {symbol}")
        if len(account.positions) >= self.config.max_open_positions:
            return self._reject(
                f"at max open positions ({self.config.max_open_positions})"
            )

        equity = account.equity
        if equity <= 0:
            return self._reject("no equity available")

        stop_price = self._resolve_stop(signal, price, side)
        stop_distance = abs(price - stop_price)
        if stop_distance <= 0:
            return self._reject("stop distance is zero")

        # Risk-based size: lose exactly `risk_per_trade` of equity if the stop hits.
        risk_budget = equity * self.config.risk_per_trade * max(0.0, min(signal.strength, 1.0))
        amount = risk_budget / stop_distance

        # Cap 1: a single position's notional.
        amount = min(amount, equity * self.config.max_position_pct / price)

        # Cap 2: total gross exposure across all positions.
        current_exposure = sum(p.notional(price) for p in account.positions.values())
        exposure_headroom = equity * self.config.max_total_exposure_pct - current_exposure
        if exposure_headroom <= 0:
            return self._reject("total exposure limit reached")
        amount = min(amount, exposure_headroom / price)

        # Cap 3: never spend more cash than the account actually has.
        if side is Side.BUY:
            amount = min(amount, account.cash / price)

        notional = amount * price
        if notional < self.min_order_notional:
            return self._reject(
                f"size {notional:,.2f} below minimum order notional {self.min_order_notional:,.2f}"
            )
        if amount <= 0:
            return self._reject("computed size is zero")

        return SizingDecision(
            amount=amount,
            stop_price=stop_price,
            take_profit_price=self._resolve_take_profit(price, side),
            reason=f"risking {risk_budget:,.2f} ({self.config.risk_per_trade:.2%} of equity)",
        )

    def _resolve_stop(self, signal: Signal, price: float, side: Side) -> float:
        """Prefer the strategy's stop, but never accept one on the wrong side."""
        default = price * (1 - self.config.stop_loss_pct * side.sign)
        stop = signal.stop_price
        if stop is None or stop <= 0:
            return default
        if side is Side.BUY and stop >= price:
            return default
        if side is Side.SELL and stop <= price:
            return default
        return stop

    def _resolve_take_profit(self, price: float, side: Side) -> float | None:
        if self.config.take_profit_pct is None:
            return None
        return price * (1 + self.config.take_profit_pct * side.sign)

    @staticmethod
    def _reject(reason: str) -> SizingDecision:
        return SizingDecision(0.0, None, None, reason)

    # ------------------------------------------------------------------
    # Protective exits
    # ------------------------------------------------------------------
    def check_protective_exit(self, position: Position, candle) -> str | None:
        """Return an exit reason if the bar breached a stop or target.

        Stops are checked before targets: when a single bar spans both levels we
        cannot know the intra-bar order, so we assume the worse outcome rather
        than flattering the backtest.
        """
        if position.side is Side.BUY:
            if position.stop_price is not None and candle.low <= position.stop_price:
                return "stop loss"
            if position.take_profit_price is not None and candle.high >= position.take_profit_price:
                return "take profit"
        else:
            if position.stop_price is not None and candle.high >= position.stop_price:
                return "stop loss"
            if position.take_profit_price is not None and candle.low <= position.take_profit_price:
                return "take profit"
        return None

    def update_trailing_stop(self, position: Position, price: float) -> bool:
        """Ratchet a trailing stop toward price. Returns True if it moved."""
        pct = self.config.trailing_stop_pct
        if not pct:
            return False
        if position.side is Side.BUY:
            candidate = price * (1 - pct)
            if position.stop_price is None or candidate > position.stop_price:
                position.stop_price = candidate
                return True
        else:
            candidate = price * (1 + pct)
            if position.stop_price is None or candidate < position.stop_price:
                position.stop_price = candidate
                return True
        return False

    def exit_fill_price(self, position: Position, candle, reason: str) -> float:
        """Price a protective exit conservatively: fill at the level, not the close."""
        if reason == "stop loss" and position.stop_price is not None:
            if position.side is Side.BUY:
                # A gap down fills below the stop, not at it.
                return min(position.stop_price, candle.open)
            return max(position.stop_price, candle.open)
        if reason == "take profit" and position.take_profit_price is not None:
            if position.side is Side.BUY:
                return max(position.take_profit_price, candle.open) if candle.open > position.take_profit_price else position.take_profit_price
            return position.take_profit_price
        return candle.close
