"""Shared fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.config import from_dict
from tradingbot.models import Candle

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_candles(closes, *, start=START, timeframe_minutes=60, spread=0.005):
    """Build candles from a list of closes, with plausible highs and lows."""
    out = []
    ts = start
    prev = closes[0]
    for close in closes:
        high = max(prev, close) * (1 + spread)
        low = min(prev, close) * (1 - spread)
        out.append(Candle(ts, prev, high, low, close, 1000.0))
        prev = close
        ts += timedelta(minutes=timeframe_minutes)
    return out


@pytest.fixture
def candles():
    return make_candles


@pytest.fixture
def config():
    """A permissive config so tests exercise logic, not incidental limits."""
    return from_dict(
        {
            "symbols": ["BTC/USDT"],
            "timeframe": "1h",
            "execution": {
                "starting_cash": 10_000.0,
                "fee_rate": 0.0,
                "slippage_pct": 0.0,
                "min_order_notional": 0.0,
            },
            "risk": {
                "risk_per_trade": 0.02,
                "max_position_pct": 0.5,
                "max_total_exposure_pct": 1.0,
                "stop_loss_pct": 0.05,
                "take_profit_pct": None,
            },
        }
    )
