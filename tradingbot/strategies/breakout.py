"""Donchian channel breakout with an ATR stop and a chandelier-style trail."""

from __future__ import annotations

from collections.abc import Sequence

from ..indicators import atr, rolling_max, rolling_min
from ..models import Candle, Position, Signal, SignalType
from .base import Strategy, register


@register
class BreakoutStrategy(Strategy):
    """Buy N-bar highs, exit on M-bar lows, with an ATR-based protective stop."""

    name = "breakout"
    default_params = {
        "entry_period": 20,
        "exit_period": 10,
        "atr_period": 14,
        "atr_stop_multiple": 2.0,
        # Require the breakout bar's volume to beat its own average by this factor.
        "volume_factor": 0.0,
    }

    def validate_params(self) -> None:
        if self.params["entry_period"] < 2 or self.params["exit_period"] < 2:
            raise ValueError("breakout: entry_period and exit_period must be at least 2")
        if self.params["exit_period"] > self.params["entry_period"]:
            raise ValueError("breakout: exit_period should not exceed entry_period")

    @property
    def warmup(self) -> int:
        return max(self.params["entry_period"], self.params["atr_period"]) + 1

    def generate(self, candles: Sequence[Candle], position: Position | None) -> Signal:
        if len(candles) < self.warmup:
            return self._hold()

        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        price = closes[-1]

        if position is not None:
            # Exit on a break of the shorter-period low.
            exit_low = rolling_min(lows[:-1], self.params["exit_period"])[-1]
            if exit_low is not None and price < exit_low:
                return Signal(SignalType.EXIT, reason=f"closed below {self.params['exit_period']}-bar low")
            return self._hold()

        # Compare against the channel excluding the current bar, so the breakout
        # is measured against prior history rather than against itself.
        channel_high = rolling_max(highs[:-1], self.params["entry_period"])[-1]
        if channel_high is None or price <= channel_high:
            return self._hold()

        if not self._volume_ok(candles):
            return self._hold()

        return Signal(
            SignalType.ENTER_LONG,
            reason=f"closed above {self.params['entry_period']}-bar high {channel_high:.2f}",
            stop_price=self._atr_stop(highs, lows, closes, price),
        )

    def _volume_ok(self, candles: Sequence[Candle]) -> bool:
        factor = self.params["volume_factor"]
        if not factor:
            return True
        window = [c.volume for c in candles[-(self.params["entry_period"] + 1) : -1]]
        if not window:
            return True
        average = sum(window) / len(window)
        return average <= 0 or candles[-1].volume >= average * factor

    def _atr_stop(self, highs, lows, closes, price: float) -> float | None:
        multiple = self.params["atr_stop_multiple"]
        if not multiple:
            return None
        values = atr(highs, lows, closes, self.params["atr_period"])
        if values[-1] is None:
            return None
        stop = price - multiple * values[-1]
        return stop if stop > 0 else None
