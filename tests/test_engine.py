"""Engine behaviour, including the guards that must hold in live trading."""

from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.engine import TradingEngine
from tradingbot.exchange.paper import PaperBroker
from tradingbot.models import HOLD, Candle, Signal, SignalType
from tradingbot.notifier import Notifier
from tradingbot.strategies.base import Strategy

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


class ScriptedSource:
    """Replays a fixed candle list, advancing one bar per fetch."""

    def __init__(self, candles, step=True):
        self.candles = candles
        self.cursor = 30
        self.step = step
        self.calls = 0

    def fetch_candles(self, symbol, timeframe, limit):
        self.calls += 1
        end = min(self.cursor, len(self.candles))
        if self.step:
            self.cursor = min(end + 1, len(self.candles))
        return self.candles[max(0, end - limit) : end]

    def close(self):
        pass


class AlwaysEnter(Strategy):
    name = "_test_always_enter"
    default_params = {}

    @property
    def warmup(self):
        return 2

    def generate(self, candles, position):
        if position is None:
            return Signal(SignalType.ENTER_LONG, reason="always")
        return HOLD


class CountingStrategy(Strategy):
    name = "_test_counting"
    default_params = {}

    def __init__(self, **params):
        super().__init__(**params)
        self.calls = 0

    @property
    def warmup(self):
        return 2

    def generate(self, candles, position):
        self.calls += 1
        return HOLD


def make_candles(closes, start=START):
    out, ts, prev = [], start, closes[0]
    for close in closes:
        out.append(Candle(ts, prev, max(prev, close) * 1.001, min(prev, close) * 0.999, close, 100.0))
        prev = close
        ts += timedelta(hours=1)
    return out


def build(config, strategy, candles, tmp_path, step=True):
    config.state_dir = str(tmp_path)
    config.execution.poll_interval = 1
    broker = PaperBroker(
        starting_cash=config.execution.starting_cash,
        fee_rate=config.execution.fee_rate,
        slippage_pct=config.execution.slippage_pct,
        data_source=ScriptedSource(candles, step=step),
    )
    return TradingEngine(config, strategy, broker, Notifier()), broker


def test_engine_opens_a_position_from_a_signal(config, tmp_path):
    candles = make_candles([100.0] * 60)
    engine, broker = build(config, AlwaysEnter(), candles, tmp_path)
    engine.tick()
    assert "BTC/USDT" in broker.get_positions()


def test_the_opened_position_carries_the_risk_managers_stop(config, tmp_path):
    config.risk.stop_loss_pct = 0.05
    config.risk.take_profit_pct = 0.1
    engine, broker = build(config, AlwaysEnter(), make_candles([100.0] * 60), tmp_path)
    engine.tick()

    position = broker.get_positions()["BTC/USDT"]
    assert position.stop_price == pytest.approx(95.0)
    assert position.take_profit_price == pytest.approx(110.0)


def test_a_strategy_is_consulted_once_per_closed_bar(config, tmp_path):
    strategy = CountingStrategy()
    # step=False means every poll returns the same bar; the strategy must not re-fire.
    engine, _ = build(config, strategy, make_candles([100.0] * 60), tmp_path, step=False)
    engine.tick()
    engine.tick()
    engine.tick()
    assert strategy.calls == 1


def test_a_stop_is_honoured_between_bars_not_only_on_a_new_one(config, tmp_path):
    config.risk.stop_loss_pct = 0.02
    config.risk.take_profit_pct = None
    candles = make_candles([100.0] * 40 + [90.0] * 20)
    engine, broker = build(config, AlwaysEnter(), candles, tmp_path)

    engine.tick()
    assert broker.get_positions()
    for _ in range(15):
        engine.tick()
        if not broker.get_positions():
            break
    assert not broker.get_positions()
    assert broker.trades and broker.trades[-1].reason == "stop loss"


def test_a_risk_halt_flattens_every_open_position(config, tmp_path):
    config.risk.max_drawdown_pct = 0.01
    config.risk.stop_loss_pct = 0.5  # keep the stop out of the way
    config.risk.take_profit_pct = None
    candles = make_candles([100.0] * 40 + [70.0] * 20)
    engine, broker = build(config, AlwaysEnter(), candles, tmp_path)

    for _ in range(20):
        engine.tick()
        if engine.risk.is_halted:
            break

    assert engine.risk.is_halted
    assert not broker.get_positions()  # halting closes out, it does not just stop entering


def test_a_halted_engine_opens_nothing_further(config, tmp_path):
    engine, broker = build(config, AlwaysEnter(), make_candles([100.0] * 60), tmp_path)
    engine.risk.restore(peak_equity=10_000.0, halted_reason="manual halt")
    engine.tick()
    assert not broker.get_positions()


def test_state_is_written_after_each_tick(config, tmp_path):
    engine, _ = build(config, AlwaysEnter(), make_candles([100.0] * 60), tmp_path)
    engine.tick()
    assert (tmp_path / "bot_state.json").exists()


def test_an_open_position_is_restored_after_a_restart(config, tmp_path):
    candles = make_candles([100.0] * 60)
    engine, broker = build(config, AlwaysEnter(), candles, tmp_path)
    engine.tick()
    original = broker.get_positions()["BTC/USDT"]

    revived, revived_broker = build(config, AlwaysEnter(), candles, tmp_path)
    revived._restore_state()

    restored = revived_broker.get_positions()["BTC/USDT"]
    assert restored.amount == pytest.approx(original.amount)
    assert restored.entry_price == pytest.approx(original.entry_price)


def test_a_halt_is_restored_after_a_restart(config, tmp_path):
    engine, _ = build(config, AlwaysEnter(), make_candles([100.0] * 60), tmp_path)
    engine.risk.restore(peak_equity=10_000.0, halted_reason="drawdown")
    engine._persist()

    revived, revived_broker = build(config, AlwaysEnter(), make_candles([100.0] * 60), tmp_path)
    revived._restore_state()
    assert revived.risk.is_halted  # a restart must not clear a circuit breaker

    revived.tick()
    assert not revived_broker.get_positions()


def test_a_failing_tick_does_not_kill_the_loop(config, tmp_path):
    engine, _ = build(config, AlwaysEnter(), make_candles([100.0] * 60), tmp_path)

    calls = []

    def exploding_tick():
        calls.append(1)
        raise RuntimeError("exchange on fire")

    engine.tick = exploding_tick
    engine.run(max_iterations=3)
    assert len(calls) == 3  # the loop kept going despite every tick failing


def test_run_stops_at_max_iterations(config, tmp_path):
    engine, _ = build(config, CountingStrategy(), make_candles([100.0] * 200), tmp_path)
    engine.run(max_iterations=4)
    assert engine._iterations == 4


def test_stop_requests_are_honoured(config, tmp_path):
    engine, _ = build(config, CountingStrategy(), make_candles([100.0] * 200), tmp_path)
    engine.stop()
    engine.run(max_iterations=100)
    assert engine._iterations == 0


def test_too_little_data_is_skipped_rather_than_traded_on(config, tmp_path):
    engine, broker = build(config, AlwaysEnter(), make_candles([100.0] * 3), tmp_path)
    engine.broker.data_source.cursor = 1
    engine.tick()
    assert not broker.get_positions()
