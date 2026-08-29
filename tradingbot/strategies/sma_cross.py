"""Trend following: trade the crossover of a fast and slow moving average."""

from __future__ import annotations

from collections.abc import Sequence

from ..indicators import atr, ema, sma
from ..models import Candle, Position, Signal, SignalType
from .base import Strategy, register


@register
class SmaCrossStrategy(Strategy):
    """Go long when a fast moving average crosses above a slow one; exit on the reverse."""

    name = "sma_cross"
    default_params = {
        "fast_period": 20,
        "slow_period": 50,
        "use_ema": False,
        # Stop placed this many ATRs below entry; None falls back to the risk config.
        "atr_stop_multiple": 2.0,
        "atr_period": 14,
        # Ignore crossovers where the gap is noise rather than a real trend change.
        "min_separation_pct": 0.0,
    }

    def validate_params(self) -> None:
        if self.params["fast_period"] >= self.params["slow_period"]:
            raise ValueError("sma_cross: fast_period must be less than slow_period")
        if self.params["fast_period"] < 2:
            raise ValueError("sma_cross: fast_period must be at least 2")

    @property
    def warmup(self) -> int:
        # +1 so the previous bar's relationship is also known, which the cross needs.
        return max(self.params["slow_period"], self.params["atr_period"]) + 1

    def generate(self, candles: Sequence[Candle], position: Position | None) -> Signal:
        if len(candles) < self.warmup:
            return self._hold()

        closes = [c.close for c in candles]
        average = ema if self.params["use_ema"] else sma
        fast = average(closes, self.params["fast_period"])
        slow = average(closes, self.params["slow_period"])

        if None in (fast[-1], fast[-2], slow[-1], slow[-2]):
            return self._hold()

        prev_above = fast[-2] > slow[-2]
        now_above = fast[-1] > slow[-1]

        separation = abs(fast[-1] - slow[-1]) / slow[-1] if slow[-1] else 0.0
        if separation < self.params["min_separation_pct"]:
            return self._hold()

        if not prev_above and now_above:
            if position is not None:
                return self._hold()
            return Signal(
                SignalType.ENTER_LONG,
                reason=f"fast MA crossed above slow MA ({separation:.2%} apart)",
                stop_price=self._atr_stop(candles, closes[-1]),
            )

        if prev_above and not now_above:
            if position is not None:
                return Signal(SignalType.EXIT, reason="fast MA crossed below slow MA")
            return self._hold()

        return self._hold()

    def _atr_stop(self, candles: Sequence[Candle], price: float) -> float | None:
        multiple = self.params["atr_stop_multiple"]
        if not multiple:
            return None
        values = atr(
            [c.high for c in candles],
            [c.low for c in candles],
            [c.close for c in candles],
            self.params["atr_period"],
        )
        if values[-1] is None:
            return None
        stop = price - multiple * values[-1]
        return stop if stop > 0 else None
