"""Mean reversion: buy oversold dips, exit once momentum normalises."""

from __future__ import annotations

from collections.abc import Sequence

from ..indicators import rsi, sma
from ..models import Candle, Position, Signal, SignalType
from .base import Strategy, register


@register
class RsiReversionStrategy(Strategy):
    """Buy RSI-oversold dips inside an uptrend, exit as momentum normalises."""

    name = "rsi_reversion"
    default_params = {
        "rsi_period": 14,
        "oversold": 30.0,
        "overbought": 70.0,
        # Exit once RSI recovers past this level, before it reaches overbought.
        "exit_level": 50.0,
        # Only buy dips while price is above this trend filter (0 disables it).
        "trend_filter_period": 200,
        "stop_pct": 0.03,
    }

    def validate_params(self) -> None:
        p = self.params
        if not 0 < p["oversold"] < p["exit_level"] < p["overbought"] < 100:
            raise ValueError("rsi_reversion: require 0 < oversold < exit_level < overbought < 100")
        if p["rsi_period"] < 2:
            raise ValueError("rsi_reversion: rsi_period must be at least 2")

    @property
    def warmup(self) -> int:
        return max(self.params["rsi_period"] + 1, self.params["trend_filter_period"] or 0)

    def generate(self, candles: Sequence[Candle], position: Position | None) -> Signal:
        if len(candles) < self.warmup:
            return self._hold()

        closes = [c.close for c in candles]
        values = rsi(closes, self.params["rsi_period"])
        current = values[-1]
        if current is None:
            return self._hold()

        if position is not None:
            if current >= self.params["exit_level"]:
                return Signal(SignalType.EXIT, reason=f"RSI recovered to {current:.1f}")
            return self._hold()

        if current > self.params["oversold"]:
            return self._hold()

        if not self._trend_ok(closes):
            return self._hold()

        price = closes[-1]
        return Signal(
            SignalType.ENTER_LONG,
            reason=f"RSI oversold at {current:.1f}",
            stop_price=price * (1 - self.params["stop_pct"]),
        )

    def _trend_ok(self, closes: Sequence[float]) -> bool:
        """Avoid catching falling knives: only buy dips inside an uptrend."""
        period = self.params["trend_filter_period"]
        if not period:
            return True
        trend = sma(closes, period)
        return trend[-1] is not None and closes[-1] > trend[-1]
