"""Pure-Python technical indicators.

Every function takes a sequence of floats (oldest first) and returns a list of the
same length, with `None` padding until the indicator has enough data. Keeping the
output aligned with the input means a strategy can always index by bar position.
"""

from __future__ import annotations

from collections.abc import Sequence

Series = list[float | None]


def sma(values: Sequence[float], period: int) -> Series:
    """Simple moving average."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    """Exponential moving average, seeded with the first SMA so it is deterministic."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> Series:
    """Wilder's relative strength index."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out

    gains = losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi_from_averages(avg_gain, avg_loss)
    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    out = [highs[0] - lows[0]] if highs else []
    for i in range(1, len(highs)):
        prev_close = closes[i - 1]
        out.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
        )
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Series:
    """Average true range, smoothed the Wilder way."""
    tr = true_range(highs, lows, closes)
    out: Series = [None] * len(tr)
    if len(tr) < period:
        return out
    prev = sum(tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(tr)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def stddev(values: Sequence[float], period: int) -> Series:
    """Rolling population standard deviation."""
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / period
        out[i] = variance**0.5
    return out


def bollinger(
    values: Sequence[float], period: int = 20, num_std: float = 2.0
) -> tuple[Series, Series, Series]:
    """Return (lower, middle, upper) Bollinger bands."""
    middle = sma(values, period)
    sd = stddev(values, period)
    lower: Series = [None] * len(values)
    upper: Series = [None] * len(values)
    for i, (m, s) in enumerate(zip(middle, sd)):
        if m is not None and s is not None:
            lower[i] = m - num_std * s
            upper[i] = m + num_std * s
    return lower, middle, upper


def rolling_max(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = max(values[i - period + 1 : i + 1])
    return out


def rolling_min(values: Sequence[float], period: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = min(values[i - period + 1 : i + 1])
    return out
