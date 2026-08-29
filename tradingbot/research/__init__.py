"""Contract due-diligence research.

Reads public chain data about a token contract and reports what powers exist,
who holds them, and what the deploying address has built before.
"""

from .analyzer import ContractResearcher, review_contract
from .models import ContractFacts, ContractReport, DeployerProfile, Finding, Severity
from .sources import (
    CHAINS,
    AuthError,
    EtherscanSource,
    SourceError,
    is_address,
    normalise_chain,
)

__all__ = [
    "AuthError", "CHAINS", "ContractFacts", "ContractReport", "ContractResearcher",
    "DeployerProfile", "EtherscanSource", "Finding", "Severity", "SourceError",
    "is_address", "normalise_chain", "review_contract",
]
