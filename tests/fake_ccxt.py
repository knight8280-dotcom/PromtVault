"""A stand-in for the ccxt package, so the live path can be tested offline.

It mimics the parts of the ccxt surface CcxtBroker actually touches: the error
hierarchy, an exchange class, and the handful of methods the adapter calls.
"""

from __future__ import annotations

import sys
import types


class BaseError(Exception):
    pass


class NetworkError(BaseError):
    pass


class RequestTimeout(NetworkError):
    pass


class ExchangeNotAvailable(NetworkError):
    pass


class InsufficientFunds(BaseError):
    pass


class FakeExchange:
    """Records calls and returns canned responses."""

    # Populated per test before the broker is constructed.
    ohlcv: list = []
    ticker: dict = {"last": 100.0}
    balance: dict = {"free": {"USDT": 5_000.0}}
    order_response: dict | None = None
    sandbox_supported: bool = True
    # Exceptions to raise on successive calls before succeeding.
    failures: list = []

    def __init__(self, options=None):
        self.options = options or {}
        self.calls = []
        self.sandbox = False
        self._failures = list(type(self).failures)

    # -- setup -------------------------------------------------------
    def set_sandbox_mode(self, enabled):
        if not type(self).sandbox_supported:
            raise BaseError("sandbox not supported")
        self.sandbox = enabled

    def amount_to_precision(self, symbol, amount):
        return f"{float(amount):.6f}"

    def price_to_precision(self, symbol, price):
        return f"{float(price):.2f}"

    # -- data --------------------------------------------------------
    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self._maybe_fail("fetch_ohlcv")
        self.calls.append(("fetch_ohlcv", symbol, timeframe, since, limit))
        rows = type(self).ohlcv
        if since is not None:
            rows = [r for r in rows if r[0] >= since]
        return rows[: limit or len(rows)]

    def fetch_ticker(self, symbol):
        self._maybe_fail("fetch_ticker")
        self.calls.append(("fetch_ticker", symbol))
        return type(self).ticker

    def fetch_balance(self):
        self._maybe_fail("fetch_balance")
        self.calls.append(("fetch_balance",))
        return type(self).balance

    # -- trading -----------------------------------------------------
    def create_order(self, symbol, order_type, side, amount, price=None):
        self._maybe_fail("create_order")
        self.calls.append(("create_order", symbol, order_type, side, amount, price))
        if type(self).order_response is not None:
            return type(self).order_response
        fill_price = price or type(self).ticker.get("last", 100.0)
        return {
            "id": "order-1",
            "filled": float(amount),
            "average": float(fill_price),
            "fee": {"cost": float(amount) * float(fill_price) * 0.001},
            "status": "closed",
            "timestamp": 1_700_000_000_000,
        }

    def close(self):
        self.calls.append(("close",))

    def _maybe_fail(self, _name):
        if self._failures:
            raise self._failures.pop(0)


def install(monkeypatch, **exchange_attrs):
    """Install the fake ccxt module and configure the exchange class."""
    module = types.ModuleType("ccxt")
    module.BaseError = BaseError
    module.NetworkError = NetworkError
    module.RequestTimeout = RequestTimeout
    module.ExchangeNotAvailable = ExchangeNotAvailable
    module.InsufficientFunds = InsufficientFunds

    # Reset class-level canned responses between tests.
    defaults = {
        "ohlcv": [],
        "ticker": {"last": 100.0},
        "balance": {"free": {"USDT": 5_000.0}},
        "order_response": None,
        "sandbox_supported": True,
        "failures": [],
    }
    for key, value in {**defaults, **exchange_attrs}.items():
        setattr(FakeExchange, key, value)

    module.binance = FakeExchange
    module.kraken = FakeExchange
    monkeypatch.setitem(sys.modules, "ccxt", module)
    return module
