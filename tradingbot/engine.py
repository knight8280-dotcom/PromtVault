"""The live trading loop, used for both paper and live modes.

The loop is deliberately boring: wait for a new closed bar, ask the strategy for
an intent, ask the risk manager whether it is allowed and how big, place the
order, persist state. Everything that can stop it losing money happens before
the order is placed, not after.
"""

from __future__ import annotations

import logging
import signal as signal_module
import time
from datetime import datetime, timezone

from .config import Config
from .exchange.base import Broker
from .exchange.paper import InsufficientFunds, PaperBroker
from .models import AccountState, Candle, Order, SignalType
from .notifier import Notifier
from .risk import RiskManager
from .state import load_state, save_state, state_path
from .strategies.base import Strategy

log = logging.getLogger(__name__)


class TradingEngine:
    """Drives strategies against a broker on a fixed polling interval."""

    def __init__(
        self,
        config: Config,
        strategy: Strategy,
        broker: Broker,
        notifier: Notifier | None = None,
    ) -> None:
        self.config = config
        self.strategy = strategy
        self.broker = broker
        self.notifier = notifier or Notifier()
        self.risk = RiskManager(config.risk, config.execution.min_order_notional)
        self.state_file = state_path(config.state_dir)

        self._running = False
        self._stop_requested = False
        # Last bar timestamp acted on per symbol, so a bar is never traded twice.
        self._last_bar: dict[str, datetime] = {}
        self._iterations = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self, max_iterations: int | None = None) -> None:
        """Poll until stopped. `max_iterations` bounds the loop for tests."""
        self._install_signal_handlers()
        self._restore_state()
        self._running = True

        mode = "LIVE" if self.config.is_live else "PAPER"
        self.notifier.send(
            f"{mode} trading started: {self.strategy.describe()} on "
            f"{', '.join(self.config.symbols)} @ {self.config.timeframe}"
        )

        try:
            while self._running and not self._stop_requested:
                if max_iterations is not None and self._iterations >= max_iterations:
                    break
                self._iterations += 1
                try:
                    self.tick()
                except Exception as exc:  # noqa: BLE001 - one bad poll must not kill the bot
                    log.exception("error during tick")
                    self.notifier.error(f"tick failed: {exc}")

                if self._stop_requested or (
                    max_iterations is not None and self._iterations >= max_iterations
                ):
                    break
                self._sleep(self.config.execution.poll_interval)
        finally:
            self._shutdown()

    def stop(self) -> None:
        self._stop_requested = True

    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("received signal %s; finishing this cycle then stopping", signum)
            self.stop()

        for sig in (signal_module.SIGINT, signal_module.SIGTERM):
            try:
                signal_module.signal(sig, handler)
            except ValueError:
                # Not on the main thread (e.g. under a test runner); skip quietly.
                pass

    def _sleep(self, seconds: float) -> None:
        """Sleep in short slices so a stop request is honoured promptly."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not self._stop_requested:
            time.sleep(min(1.0, deadline - time.monotonic()))

    def _shutdown(self) -> None:
        self._running = False
        self._persist()
        self.notifier.send(
            f"trading stopped after {self._iterations} cycles; "
            f"{len(self.broker.get_positions())} position(s) left open"
        )
        self.broker.close()

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------
    def tick(self) -> None:
        """Process one polling cycle across every configured symbol."""
        marks: dict[str, float] = {}
        for symbol in self.config.symbols:
            candles = self._fetch(symbol)
            if not candles:
                continue
            marks[symbol] = candles[-1].close
            self._process_symbol(symbol, candles)

        equity = self.broker.get_equity(marks)
        was_halted = self.risk.is_halted
        self.risk.observe_equity(equity, datetime.now(timezone.utc))
        if self.risk.is_halted and not was_halted:
            self.notifier.halted(self.risk.halt_reason or "unknown")
            self._flatten_all(marks)

        self._persist()

    def _fetch(self, symbol: str) -> list[Candle]:
        limit = max(self.strategy.warmup + 5, 100)
        candles = self.broker.fetch_candles(symbol, self.config.timeframe, limit)
        if len(candles) < self.strategy.warmup:
            log.warning(
                "%s: only %d candles, need %d for %s",
                symbol, len(candles), self.strategy.warmup, self.strategy.name,
            )
            return []
        return candles

    def _process_symbol(self, symbol: str, candles: list[Candle]) -> None:
        latest = candles[-1]
        price = latest.close
        if isinstance(self.broker, PaperBroker):
            self.broker.mark(symbol, price)

        position = self.broker.get_positions().get(symbol)

        # Protective exits are checked every cycle, not only on a new bar.
        if position is not None:
            if self.risk.update_trailing_stop(position, price):
                log.debug("%s trailing stop moved to %.2f", symbol, position.stop_price)
            reason = self.risk.check_protective_exit(position, latest)
            if reason:
                self._close(symbol, price, reason)
                return

        # Strategy decisions are made once per closed bar.
        if self._last_bar.get(symbol) == latest.timestamp:
            return
        self._last_bar[symbol] = latest.timestamp

        signal = self.strategy.generate(candles, position)
        if signal.type is SignalType.HOLD:
            return

        if signal.type is SignalType.EXIT:
            if position is not None:
                self._close(symbol, price, signal.reason or "strategy exit")
            return

        if position is not None or not signal.is_entry:
            return

        account = AccountState(
            cash=self.broker.get_cash(),
            equity=self.broker.get_equity({symbol: price}),
            positions=dict(self.broker.get_positions()),
        )
        decision = self.risk.size_entry(signal, price, account, symbol)
        if not decision.approved:
            log.info("%s entry skipped: %s", symbol, decision.reason)
            return

        try:
            fill = self.broker.submit(Order(symbol, signal.side, decision.amount), latest.timestamp)
        except InsufficientFunds as exc:
            log.warning("%s entry rejected: %s", symbol, exc)
            return

        if fill is None:
            log.warning("%s entry did not fill", symbol)
            return

        opened = self.broker.get_positions().get(symbol)
        if opened is not None:
            opened.stop_price = decision.stop_price
            opened.take_profit_price = decision.take_profit_price

        self.notifier.trade_opened(
            symbol, signal.side.value, fill.amount, fill.price, signal.reason
        )
        self._persist()

    def _close(self, symbol: str, price: float, reason: str) -> None:
        position = self.broker.get_positions().get(symbol)
        if position is None:
            return

        if isinstance(self.broker, PaperBroker):
            self.broker.reference_price[symbol] = price

        order = Order(symbol, position.side.opposite, position.amount, client_id=reason, reduce_only=True)
        fill = self.broker.submit(order, datetime.now(timezone.utc))
        if fill is None:
            log.error("%s: exit order did not fill — position is still open", symbol)
            self.notifier.error(f"{symbol} exit failed; position still open")
            return

        pnl = (fill.price - position.entry_price) * position.amount * position.side.sign
        pnl -= position.fees_paid + fill.fee
        self.risk.record_realized_pnl(pnl, self.broker.get_equity({symbol: fill.price}))
        self.notifier.trade_closed(symbol, pnl, fill.price, reason)
        if self.risk.is_halted:
            self.notifier.halted(self.risk.halt_reason or "unknown")
        self._persist()

    def _flatten_all(self, marks: dict[str, float]) -> None:
        """Close every position — used when a circuit breaker trips."""
        for symbol in list(self.broker.get_positions()):
            price = marks.get(symbol) or self.broker.last_price(symbol)
            if price is None:
                log.error("%s: cannot flatten, no price available", symbol)
                continue
            self._close(symbol, price, "risk halt")

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def _restore_state(self) -> None:
        saved = load_state(self.state_file)
        if not saved:
            return

        positions = saved.get("positions", {})
        if positions:
            log.info("restoring %d open position(s) from %s", len(positions), self.state_file)
            adopt = getattr(self.broker, "adopt_positions", None)
            if callable(adopt):
                adopt(positions)
            elif isinstance(self.broker, PaperBroker):
                self.broker.positions = dict(positions)
                self.broker.cash = float(saved.get("cash", self.broker.cash))

        self.risk.restore(
            peak_equity=float(saved.get("peak_equity", 0.0)),
            realized_today=float(saved.get("realized_today", 0.0)),
            halted_reason=saved.get("halted_reason"),
        )
        if saved.get("halted_reason"):
            log.warning("restored halt state: %s", saved["halted_reason"])

    def _persist(self) -> None:
        try:
            save_state(
                self.state_file,
                positions=self.broker.get_positions(),
                cash=self.broker.get_cash(),
                peak_equity=self.risk.peak_equity,
                realized_today=self.risk.realized_today,
                halted_reason=self.risk.halt_reason,
                updated_at=datetime.now(timezone.utc),
            )
        except OSError as exc:
            log.error("could not save state: %s", exc)
