"""Funding-rate carry: a structural edge rather than a price forecast."""

from .models import (
    BasisPosition,
    CarryCosts,
    CarryOpportunity,
    FundingHistory,
    FundingRate,
)
from .scanner import CarryScanner, ScanResult, format_scan
from .sources import PERP_VENUES, FundingSource, FundingSourceError

__all__ = [
    "BasisPosition", "CarryCosts", "CarryOpportunity", "CarryScanner",
    "FundingHistory", "FundingRate", "FundingSource", "FundingSourceError",
    "PERP_VENUES", "ScanResult", "format_scan", "CcxtFundingSource",
]


def __getattr__(name: str):
    """Import the ccxt-backed source lazily so ccxt stays optional."""
    if name == "CcxtFundingSource":
        from .sources import CcxtFundingSource

        return CcxtFundingSource
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
