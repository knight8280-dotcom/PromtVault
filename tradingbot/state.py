"""Crash-safe persistence of open positions and risk counters.

A restart must not lose track of an open position, so state is written after
every change using a write-and-rename so a crash mid-write cannot corrupt it.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from .models import Position, Side

log = logging.getLogger(__name__)
STATE_VERSION = 1


def state_path(state_dir: str | Path, name: str = "bot_state.json") -> Path:
    return Path(state_dir) / name


def save_state(
    path: str | Path,
    *,
    positions: dict[str, Position],
    cash: float,
    peak_equity: float,
    realized_today: float,
    halted_reason: str | None,
    updated_at: datetime,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "updated_at": updated_at.isoformat(),
        "cash": cash,
        "peak_equity": peak_equity,
        "realized_today": realized_today,
        "halted_reason": halted_reason,
        "positions": {symbol: _position_to_dict(p) for symbol, p in positions.items()},
    }

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)  # atomic on POSIX and Windows


def load_state(path: str | Path) -> dict | None:
    """Load saved state, or None if there is none. Corrupt state is not fatal."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        log.error("state file %s is corrupt and will be ignored", path)
        return None

    version = payload.get("version")
    if version != STATE_VERSION:
        log.warning("ignoring state file written by version %s (expected %s)", version, STATE_VERSION)
        return None

    payload["positions"] = {
        symbol: _position_from_dict(symbol, d) for symbol, d in payload.get("positions", {}).items()
    }
    return payload


def _position_to_dict(p: Position) -> dict:
    return {
        "side": p.side.value,
        "amount": p.amount,
        "entry_price": p.entry_price,
        "opened_at": p.opened_at.isoformat(),
        "stop_price": p.stop_price,
        "take_profit_price": p.take_profit_price,
        "fees_paid": p.fees_paid,
    }


def _position_from_dict(symbol: str, d: dict) -> Position:
    return Position(
        symbol=symbol,
        side=Side(d["side"]),
        amount=float(d["amount"]),
        entry_price=float(d["entry_price"]),
        opened_at=datetime.fromisoformat(d["opened_at"]),
        stop_price=d.get("stop_price"),
        take_profit_price=d.get("take_profit_price"),
        fees_paid=float(d.get("fees_paid", 0.0)),
    )
