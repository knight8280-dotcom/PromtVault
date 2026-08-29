"""On-disk CSV cache for OHLCV data, so backtests do not re-download history."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import Candle, utc_from_ms

HEADER = ["timestamp", "open", "high", "low", "close", "volume"]


def cache_path(data_dir: str | Path, symbol: str, timeframe: str) -> Path:
    safe = symbol.replace("/", "-").replace(":", "-")
    return Path(data_dir) / f"{safe}_{timeframe}.csv"


def save(path: str | Path, candles: list[Candle]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(c.as_row() for c in candles)
    return path


def load(path: str | Path) -> list[Candle]:
    """Read candles from CSV, tolerating both ms timestamps and ISO dates."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no cached data at {path}")

    out: list[Candle] = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        missing = set(HEADER) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing column(s): {', '.join(sorted(missing))}")
        for row in reader:
            out.append(
                Candle(
                    timestamp=_parse_timestamp(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"] or 0.0),
                )
            )
    out.sort(key=lambda c: c.timestamp)
    return out


def _parse_timestamp(raw: str):
    from datetime import datetime, timezone

    raw = raw.strip()
    if raw.isdigit():
        value = int(raw)
        # Heuristic: 10-digit values are seconds, longer ones milliseconds.
        return utc_from_ms(value if value > 10**11 else value * 1000)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def merge(existing: list[Candle], fresh: list[Candle]) -> list[Candle]:
    """Combine two candle lists, de-duplicating by timestamp (fresh wins)."""
    by_time = {c.timestamp: c for c in existing}
    by_time.update({c.timestamp: c for c in fresh})
    return [by_time[t] for t in sorted(by_time)]
