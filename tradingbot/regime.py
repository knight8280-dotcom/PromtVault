"""Market regime detection, and gating strategies on it.

Every strategy encodes an assumption about the market. Trend following needs
price to travel; mean reversion needs it to oscillate around a level. Run either
in the wrong regime and it bleeds — a crossover strategy in a choppy market
whipsaws, paying fees on every false start.

Rather than trying to make one strategy handle all conditions, this measures the
regime and lets a strategy decline to trade when its premise does not hold. Not
trading is a position, and usually the cheapest one available.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .indicators import atr, sma
from .models import Candle, Position, Signal, SignalType
from .strategies.base import Strategy


class Regime(str, Enum):
    TRENDING = "trending"
    CHOPPY = "choppy"
    VOLATILE = "volatile"
    QUIET = "quiet"
    UNKNOWN = "unknown"


def efficiency_ratio(closes: Sequence[float], period: int) -> float | None:
    """Kaufman's efficiency ratio: net movement divided by total path length.

    1.0 is a straight line; near 0 is a random walk that ended where it started.
    It is the cleanest single measure of "is this market going anywhere", and it
    needs no parameters beyond the window.
    """
    if len(closes) < period + 1:
        return None

    window = closes[-(period + 1):]
    net = abs(window[-1] - window[0])
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    if path == 0:
        return 0.0
    return net / path


def normalized_atr(candles: Sequence[Candle], period: int = 14) -> float | None:
    """ATR as a fraction of price, so it is comparable across assets."""
    if len(candles) < period + 1:
        return None
    values = atr(
        [c.high for c in candles], [c.low for c in candles], [c.close for c in candles], period
    )
    if values[-1] is None or candles[-1].close <= 0:
        return None
    return values[-1] / candles[-1].close


@dataclass
class RegimeReading:
    """What the market looks like right now, and why."""

    regime: Regime
    efficiency: float | None
    volatility: float | None
    volatility_percentile: float | None
    reason: str = ""

    @property
    def is_trending(self) -> bool:
        return self.regime is Regime.TRENDING

    @property
    def is_choppy(self) -> bool:
        return self.regime is Regime.CHOPPY

    @property
    def tradable_for_trend(self) -> bool:
        """Trend strategies want direction and enough movement to pay for fees."""
        return self.regime in (Regime.TRENDING, Regime.VOLATILE)

    @property
    def tradable_for_reversion(self) -> bool:
        """Mean reversion wants oscillation, not a one-way market."""
        return self.regime in (Regime.CHOPPY, Regime.QUIET)


class RegimeDetector:
    """Classifies the current market from price action alone."""

    def __init__(
        self,
        *,
        period: int = 30,
        atr_period: int = 14,
        trend_threshold: float = 0.35,
        chop_threshold: float = 0.15,
        volatility_lookback: int = 100,
        high_volatility_percentile: float = 0.8,
        low_volatility_percentile: float = 0.2,
    ) -> None:
        if not 0 < chop_threshold < trend_threshold < 1:
            raise ValueError("require 0 < chop_threshold < trend_threshold < 1")
        self.period = period
        self.atr_period = atr_period
        self.trend_threshold = trend_threshold
        self.chop_threshold = chop_threshold
        self.volatility_lookback = volatility_lookback
        self.high_volatility_percentile = high_volatility_percentile
        self.low_volatility_percentile = low_volatility_percentile

    @property
    def warmup(self) -> int:
        return max(self.period, self.atr_period, self.volatility_lookback) + 1

    def detect(self, candles: Sequence[Candle]) -> RegimeReading:
        if len(candles) < self.period + 1:
            return RegimeReading(Regime.UNKNOWN, None, None, None, "not enough data")

        closes = [c.close for c in candles]
        efficiency = efficiency_ratio(closes, self.period)
        volatility = normalized_atr(candles, self.atr_period)
        percentile = self._volatility_percentile(candles, volatility)

        if efficiency is None:
            return RegimeReading(Regime.UNKNOWN, None, volatility, percentile, "no efficiency reading")

        # Volatility decides the flavour; efficiency decides the direction question.
        if efficiency >= self.trend_threshold:
            return RegimeReading(
                Regime.TRENDING, efficiency, volatility, percentile,
                f"efficiency {efficiency:.2f} >= {self.trend_threshold:.2f}: price is travelling",
            )

        if efficiency <= self.chop_threshold:
            if percentile is not None and percentile >= self.high_volatility_percentile:
                return RegimeReading(
                    Regime.VOLATILE, efficiency, volatility, percentile,
                    f"efficiency {efficiency:.2f} with volatility in the "
                    f"{percentile:.0%} percentile: violent but directionless",
                )
            if percentile is not None and percentile <= self.low_volatility_percentile:
                return RegimeReading(
                    Regime.QUIET, efficiency, volatility, percentile,
                    f"efficiency {efficiency:.2f} with volatility in the "
                    f"{percentile:.0%} percentile: going nowhere, slowly",
                )
            return RegimeReading(
                Regime.CHOPPY, efficiency, volatility, percentile,
                f"efficiency {efficiency:.2f} <= {self.chop_threshold:.2f}: whipsaw territory",
            )

        return RegimeReading(
            Regime.CHOPPY, efficiency, volatility, percentile,
            f"efficiency {efficiency:.2f} is between thresholds: no clear regime",
        )

    def _volatility_percentile(self, candles: Sequence[Candle], current: float | None) -> float | None:
        """Where current volatility sits within its own recent history."""
        if current is None or len(candles) < self.atr_period + 10:
            return None

        window = candles[-self.volatility_lookback:] if len(candles) > self.volatility_lookback else candles
        values = atr(
            [c.high for c in window], [c.low for c in window], [c.close for c in window],
            self.atr_period,
        )
        history = [
            v / window[i].close
            for i, v in enumerate(values)
            if v is not None and window[i].close > 0
        ]
        if len(history) < 10:
            return None
        return sum(1 for v in history if v <= current) / len(history)


class RegimeGatedStrategy(Strategy):
    """Wraps a strategy so it only enters when the regime suits it.

    Exits are never gated. A position opened in one regime must still be closable
    in another — refusing to exit because conditions changed is how a small loss
    becomes a large one.
    """

    name = "regime_gated"
    default_params: dict = {}

    def __init__(
        self,
        inner: Strategy,
        detector: RegimeDetector | None = None,
        *,
        allow: str = "trend",
    ) -> None:
        if allow not in ("trend", "reversion", "any"):
            raise ValueError("allow must be 'trend', 'reversion' or 'any'")
        self.inner = inner
        self.detector = detector or RegimeDetector()
        self.allow = allow
        self.params = dict(inner.params)
        self.name = f"regime_gated({inner.name})"
        #: Populated as bars are processed, so a run can report what it skipped.
        self.blocked_entries: dict[str, int] = {}

    @property
    def warmup(self) -> int:
        return max(self.inner.warmup, self.detector.warmup)

    def generate(self, candles: Sequence[Candle], position: Position | None) -> Signal:
        signal = self.inner.generate(candles, position)

        # Exits and holds always pass through untouched.
        if signal.type is not SignalType.ENTER_LONG and signal.type is not SignalType.ENTER_SHORT:
            return signal

        reading = self.detector.detect(candles)
        if self._permits(reading):
            return signal

        key = reading.regime.value
        self.blocked_entries[key] = self.blocked_entries.get(key, 0) + 1
        return Signal(SignalType.HOLD, reason=f"regime {reading.regime.value}: {reading.reason}")

    def _permits(self, reading: RegimeReading) -> bool:
        if self.allow == "any":
            return True
        if reading.regime is Regime.UNKNOWN:
            return False  # no reading means no confidence, so no entry
        if self.allow == "trend":
            return reading.tradable_for_trend
        return reading.tradable_for_reversion

    def describe(self) -> str:
        return f"regime_gated[{self.allow}]({self.inner.describe()})"


def regime_summary(candles: Sequence[Candle], detector: RegimeDetector | None = None) -> dict:
    """Distribution of regimes across a dataset, for sizing up an instrument."""
    detector = detector or RegimeDetector()
    counts: dict[str, int] = {}
    step = max(1, len(candles) // 500)  # sample rather than recompute on every bar

    for i in range(detector.period + 1, len(candles), step):
        reading = detector.detect(candles[: i + 1])
        counts[reading.regime.value] = counts.get(reading.regime.value, 0) + 1

    total = sum(counts.values()) or 1
    return {regime: count / total for regime, count in sorted(counts.items())}
