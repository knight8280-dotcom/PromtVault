"""Pre-flight checks for live trading.

Run before the first live session. Every check is read-only — this places no
orders and moves no funds. The point is to fail on the ground rather than
discovering a misconfiguration with real money in the market.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum

from .config import Config

log = logging.getLogger(__name__)


class Status(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class Check:
    name: str
    status: Status
    message: str
    fix: str = ""


@dataclass
class PreflightReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: Status, message: str, fix: str = "") -> None:
        self.checks.append(Check(name, status, message, fix))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.WARN]

    @property
    def ready(self) -> bool:
        return not self.failures


def run_preflight(config: Config, broker_factory=None) -> PreflightReport:
    """Check everything that can be checked without placing an order."""
    report = PreflightReport()
    _check_credentials(config, report)
    _check_locks(config, report)
    _check_risk(config, report)

    broker = _connect(config, report, broker_factory)
    if broker is None:
        return report

    try:
        _check_account(config, broker, report)
        _check_markets(config, broker, report)
    finally:
        try:
            broker.close()
        except Exception:  # noqa: BLE001 - closing must not mask a real result
            log.debug("ignoring error while closing broker", exc_info=True)

    return report


# ----------------------------------------------------------------------
def _check_credentials(config: Config, report: PreflightReport) -> None:
    exchange = config.exchange
    key = os.environ.get(exchange.api_key_env, "")
    secret = os.environ.get(exchange.api_secret_env, "")

    if not key or not secret:
        report.add(
            "API credentials", Status.FAIL,
            f"${exchange.api_key_env} and/or ${exchange.api_secret_env} are not set",
            f"Create an API key on {exchange.name} with TRADE permission only, then: "
            f"export {exchange.api_key_env}=... and export {exchange.api_secret_env}=...",
        )
        return

    report.add(
        "API credentials", Status.PASS,
        f"key found in ${exchange.api_key_env} (…{key[-4:]})",
    )

    # A seed phrase is never an exchange API key. Catch the confusion loudly.
    if len(key.split()) >= 12:
        report.add(
            "Credential type", Status.FAIL,
            "that value looks like a seed phrase, not an exchange API key",
            "CBot trades on exchanges via API keys and never uses a wallet seed "
            "phrase or private key. Anything asking for a seed phrase can drain "
            "your wallet. Revoke that phrase's wallet and use an exchange API key.",
        )


def _check_locks(config: Config, report: PreflightReport) -> None:
    if not config.execution.confirm_live:
        report.add(
            "Live confirmation", Status.WARN,
            "execution.confirm_live is false, so `live` will refuse to start",
            "Set `confirm_live: true` in your config when you are ready to trade live.",
        )
    else:
        report.add("Live confirmation", Status.PASS, "execution.confirm_live is set")

    if config.exchange.testnet:
        report.add(
            "Venue", Status.PASS,
            f"{config.exchange.name} TESTNET — no real funds at risk",
        )
    else:
        report.add(
            "Venue", Status.WARN,
            f"{config.exchange.name} PRODUCTION — real funds will be traded",
            "Run on the testnet first until the strategy behaves as you expect.",
        )


def _check_risk(config: Config, report: PreflightReport) -> None:
    risk = config.risk
    report.add(
        "Risk settings", Status.PASS,
        f"{risk.risk_per_trade:.2%} per trade, max {risk.max_open_positions} positions, "
        f"daily loss cap {risk.max_daily_loss_pct:.0%}, drawdown halt {risk.max_drawdown_pct:.0%}",
    )

    if risk.risk_per_trade > 0.02:
        report.add(
            "Risk per trade", Status.WARN,
            f"{risk.risk_per_trade:.2%} of equity per trade is aggressive",
            "1% or less is a common starting point; a losing streak compounds fast.",
        )
    if risk.allow_shorts:
        report.add(
            "Short selling", Status.WARN,
            "shorts are enabled — losses on a short are unbounded",
            "Leave allow_shorts off until you have run the strategy long-only.",
        )


def _connect(config: Config, report: PreflightReport, broker_factory):
    from .exchange.ccxt_adapter import ExchangeError

    if report.failures:
        report.add("Exchange connection", Status.SKIP, "skipped — fix the failures above")
        return None

    try:
        if broker_factory is not None:
            return broker_factory(config)
        from .exchange.ccxt_adapter import CcxtBroker

        return CcxtBroker(config.exchange, allow_trading=True)
    except ExchangeError as exc:
        report.add(
            "Exchange connection", Status.FAIL, str(exc),
            "Check the exchange name, your keys, and whether the venue offers a sandbox.",
        )
        return None


def _check_account(config: Config, broker, report: PreflightReport) -> None:
    from .exchange.ccxt_adapter import ExchangeError

    quote = config.symbols[0].split("/")[-1] if config.symbols else "USDT"
    try:
        cash = broker.get_cash(quote)
    except ExchangeError as exc:
        report.add(
            "Account access", Status.FAIL, f"could not read your balance: {exc}",
            "The key may lack read permission, or be restricted to another IP.",
        )
        return

    report.add("Account access", Status.PASS, f"balance readable: {cash:,.2f} {quote}")

    if cash <= 0:
        report.add(
            "Tradable balance", Status.FAIL, f"no {quote} available to trade",
            f"Deposit {quote} into the account this key belongs to "
            f"({'testnet' if config.exchange.testnet else 'production'}).",
        )
        return

    # A position must clear the exchange minimum while still risking only the
    # configured fraction of equity; too little capital makes that impossible.
    smallest = config.execution.min_order_notional
    implied = cash * config.risk.max_position_pct
    if implied < smallest:
        report.add(
            "Tradable balance", Status.WARN,
            f"{cash:,.2f} {quote} allows a maximum position of {implied:,.2f}, "
            f"below the {smallest:,.2f} minimum order size",
            "Add funds, raise risk.max_position_pct, or trade a venue with a "
            "smaller minimum — otherwise every entry will be skipped.",
        )
    else:
        report.add(
            "Tradable balance", Status.PASS,
            f"{cash:,.2f} {quote} supports positions up to {implied:,.2f}",
        )


def _check_markets(config: Config, broker, report: PreflightReport) -> None:
    client = getattr(broker, "client", None)
    loader = getattr(client, "load_markets", None)
    if not callable(loader):
        report.add("Symbols", Status.SKIP, "this broker cannot list markets")
        return

    try:
        markets = loader()
    except Exception as exc:  # noqa: BLE001 - any failure here is informational
        report.add("Symbols", Status.WARN, f"could not list markets: {exc}")
        return

    missing = [s for s in config.symbols if s not in markets]
    if missing:
        report.add(
            "Symbols", Status.FAIL,
            f"not tradable on {config.exchange.name}: {', '.join(missing)}",
            "Check the exact symbol spelling for this venue (BTC/USDT vs BTC/USD).",
        )
        return

    report.add("Symbols", Status.PASS, f"all tradable: {', '.join(config.symbols)}")

    for symbol in config.symbols:
        limits = (markets.get(symbol) or {}).get("limits") or {}
        venue_min = (limits.get("cost") or {}).get("min")
        if venue_min and venue_min > config.execution.min_order_notional:
            report.add(
                f"Minimum size ({symbol})", Status.WARN,
                f"{config.exchange.name} requires at least {venue_min} per order, but "
                f"execution.min_order_notional is {config.execution.min_order_notional}",
                f"Raise execution.min_order_notional to at least {venue_min} so orders "
                f"are not rejected by the venue.",
            )
