"""State must survive a restart, and must never be trusted blindly."""

from datetime import datetime, timezone

from tradingbot.models import Position, Side
from tradingbot.state import STATE_VERSION, load_state, save_state

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def a_position():
    return Position("BTC/USDT", Side.BUY, 0.5, 30_000.0, NOW, stop_price=29_000.0, fees_paid=1.5)


def test_positions_survive_a_save_and_load(tmp_path):
    path = tmp_path / "state.json"
    save_state(
        path,
        positions={"BTC/USDT": a_position()},
        cash=1_234.5,
        peak_equity=20_000.0,
        realized_today=-50.0,
        halted_reason=None,
        updated_at=NOW,
    )
    restored = load_state(path)
    position = restored["positions"]["BTC/USDT"]

    assert restored["cash"] == 1_234.5
    assert restored["peak_equity"] == 20_000.0
    assert restored["realized_today"] == -50.0
    assert position.side is Side.BUY
    assert position.amount == 0.5
    assert position.entry_price == 30_000.0
    assert position.stop_price == 29_000.0
    assert position.opened_at == NOW


def test_a_halt_reason_survives_a_restart(tmp_path):
    path = tmp_path / "state.json"
    save_state(
        path, positions={}, cash=0.0, peak_equity=0.0, realized_today=0.0,
        halted_reason="max drawdown breached", updated_at=NOW,
    )
    # A restart must not quietly resume trading after a circuit breaker tripped.
    assert load_state(path)["halted_reason"] == "max drawdown breached"


def test_no_state_file_is_not_an_error(tmp_path):
    assert load_state(tmp_path / "missing.json") is None


def test_corrupt_state_is_ignored_rather_than_crashing(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not valid json")
    assert load_state(path) is None


def test_state_from_an_unknown_version_is_ignored(tmp_path):
    import json

    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": STATE_VERSION + 99, "positions": {}}))
    assert load_state(path) is None


def test_saving_creates_missing_directories(tmp_path):
    path = tmp_path / "deep" / "nested" / "state.json"
    save_state(
        path, positions={}, cash=1.0, peak_equity=1.0, realized_today=0.0,
        halted_reason=None, updated_at=NOW,
    )
    assert path.exists()


def test_saving_leaves_no_temp_file_behind(tmp_path):
    path = tmp_path / "state.json"
    save_state(
        path, positions={}, cash=1.0, peak_equity=1.0, realized_today=0.0,
        halted_reason=None, updated_at=NOW,
    )
    assert list(tmp_path.glob("*.tmp")) == []
