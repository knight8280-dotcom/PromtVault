"""Broker implementations: simulated (paper) and live (ccxt)."""

from .base import Broker
from .paper import InsufficientFunds, PaperBroker

__all__ = ["Broker", "PaperBroker", "InsufficientFunds", "CcxtBroker", "ExchangeError"]


def __getattr__(name: str):
    """Import the ccxt-backed broker lazily so ccxt stays an optional dependency."""
    if name in ("CcxtBroker", "ExchangeError"):
        from . import ccxt_adapter

        return getattr(ccxt_adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
