"""Event-driven backtester.

Bars are replayed one at a time and a strategy only ever sees closed candles up
to the current bar, so it cannot look ahead. Entries signalled on a bar's close
fill on the *next* bar's open, which is the earliest a real order could execute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Config
from .exchange.paper import InsufficientFunds, PaperBroker
from .metrics import Metrics, compute
from .models import AccountState, Candle, EquityPoint, Order, Side, Signal, SignalType, Trade
from .risk import RiskManager
from .strategies.base import Strategy

log = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    metrics: Metrics
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    symbol: str = ""
    strategy: str = ""
    rejections: dict[str, int] = field(default_factory=dict)
    halted_reason: str | None = None


class Backtester:
    """Replays historical candles through a strategy, broker and risk manager."""

    def __init__(self, config: Config, strategy: Strategy) -> None:
        self.config = config
        self.strategy = strategy

    def run(self, symbol: str, candles: list[Candle]) -> BacktestResult:
        exec_cfg = self.config.execution
        if len(candles) <= self.strategy.warmup + 1:
            raise ValueError(
                f"not enough data: {len(candles)} candles but {self.strategy.name} needs "
                f"more than {self.strategy.warmup + 1}"
            )

        broker = PaperBroker(
            starting_cash=exec_cfg.starting_cash,
            fee_rate=exec_cfg.fee_rate,
            slippage_pct=exec_cfg.slippage_pct,
        )
        risk = RiskManager(self.config.risk, exec_cfg.min_order_notional)

        equity_curve: list[EquityPoint] = []
        rejections: dict[str, int] = {}
        # A signal raised on bar i is executed at the open of bar i+1.
        pending: Signal | None = None
        bars_in_market = 0

        for i, candle in enumerate(candles):
            broker.reference_price[symbol] = candle.open
            if pending is not None:
                self._execute(pending, symbol, candle, broker, risk, rejections)
                pending = None

            broker.mark(symbol, candle.close)
            position = broker.get_positions().get(symbol)

            if position is not None:
                bars_in_market += 1
                risk.update_trailing_stop(position, candle.close)
                reason = risk.check_protective_exit(position, candle)
                if reason:
                    price = risk.exit_fill_price(position, candle, reason)
                    self._close(symbol, broker, risk, price, candle, reason)
                    position = None

            equity = broker.get_equity({symbol: candle.close})
            risk.observe_equity(equity, candle.timestamp)
            equity_curve.append(
                EquityPoint(
                    timestamp=candle.timestamp,
                    equity=equity,
                    cash=broker.get_cash(),
                    position_value=position.notional(candle.close) if position else 0.0,
                )
            )

            if i < self.strategy.warmup or i == len(candles) - 1:
                continue

            signal = self.strategy.generate(candles[: i + 1], broker.get_positions().get(symbol))
            if signal.type is not SignalType.HOLD:
                pending = signal

        # Close anything still open at the final bar so results reflect realised P&L.
        if symbol in broker.get_positions():
            last = candles[-1]
            self._close(symbol, broker, risk, last.close, last, "end of data")
            if equity_curve:
                equity_curve[-1] = EquityPoint(
                    timestamp=last.timestamp,
                    equity=broker.get_equity({symbol: last.close}),
                    cash=broker.get_cash(),
                )

        metrics = compute(equity_curve, broker.trades, self.config.timeframe, bars_in_market)
        return BacktestResult(
            metrics=metrics,
            trades=list(broker.trades),
            equity_curve=equity_curve,
            symbol=symbol,
            strategy=self.strategy.describe(),
            rejections=rejections,
            halted_reason=risk.halt_reason,
        )

    # ------------------------------------------------------------------
    def _execute(
        self,
        signal: Signal,
        symbol: str,
        candle: Candle,
        broker: PaperBroker,
        risk: RiskManager,
        rejections: dict[str, int],
    ) -> None:
        position = broker.get_positions().get(symbol)

        if signal.type is SignalType.EXIT:
            if position is not None:
                self._close(symbol, broker, risk, candle.open, candle, signal.reason or "signal")
            return

        if not signal.is_entry or position is not None:
            return

        account = AccountState(
            cash=broker.get_cash(),
            equity=broker.get_equity({symbol: candle.open}),
            positions=dict(broker.get_positions()),
        )
        decision = risk.size_entry(signal, candle.open, account, symbol)
        if not decision.approved:
            key = decision.reason or "rejected"
            rejections[key] = rejections.get(key, 0) + 1
            return

        try:
            fill = broker.submit(Order(symbol, signal.side, decision.amount), candle.timestamp)
        except InsufficientFunds as exc:
            rejections[str(exc)] = rejections.get(str(exc), 0) + 1
            return

        if fill is None:
            return
        opened = broker.get_positions()[symbol]
        opened.stop_price = decision.stop_price
        opened.take_profit_price = decision.take_profit_price
        log.debug("%s entry %s @ %.2f (%s)", symbol, decision.amount, fill.price, signal.reason)

    def _close(
        self,
        symbol: str,
        broker: PaperBroker,
        risk: RiskManager,
        price: float,
        candle: Candle,
        reason: str,
    ) -> None:
        position = broker.get_positions().get(symbol)
        if position is None:
            return

        broker.reference_price[symbol] = price
        order = Order(symbol, position.side.opposite, position.amount, client_id=reason)
        fill = broker.submit(order, candle.timestamp)
        if fill is None:
            return

        closed = broker.trades[-1]
        risk.record_realized_pnl(closed.net_pnl, broker.get_equity({symbol: price}))
        log.debug("%s exit @ %.2f (%s) pnl=%.2f", symbol, fill.price, reason, closed.net_pnl)


def run_backtest(config: Config, strategy: Strategy, symbol: str, candles: list[Candle]) -> BacktestResult:
    """Convenience wrapper for a single-symbol backtest."""
    return Backtester(config, strategy).run(symbol, candles)
