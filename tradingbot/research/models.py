"""Value objects for contract research."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    """How much a finding should worry you."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    GOOD = "good"

    @property
    def weight(self) -> int:
        return {
            Severity.CRITICAL: 40,
            Severity.HIGH: 20,
            Severity.MEDIUM: 8,
            Severity.LOW: 3,
            Severity.INFO: 0,
            Severity.GOOD: 0,
        }[self]

    @property
    def rank(self) -> int:
        """Sort order: worst first."""
        order = [
            Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM,
            Severity.LOW, Severity.GOOD, Severity.INFO,
        ]
        return order.index(self)


@dataclass(frozen=True)
class Finding:
    """One observation about a contract, with the evidence behind it.

    `evidence` is what was actually seen — a matched source line, an RPC result.
    A finding without evidence is an opinion, and this tool does not deal in those.
    """

    id: str
    title: str
    severity: Severity
    detail: str
    evidence: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class DeployerProfile:
    """What the chain knows about whoever deployed a contract.

    On-chain identity is an address, not a person. Nothing here says who anyone
    *is* — only what this address has done before.
    """

    address: str = ""
    first_seen: datetime | None = None
    deployed_contracts: list[dict] = field(default_factory=list)
    total_deployments: int = 0
    funded_by: str | None = None
    partial: bool = False  # true when the history was truncated by the data source

    @property
    def prior_projects(self) -> list[dict]:
        """Contracts this address deployed before the one under review."""
        return self.deployed_contracts

    def as_dict(self) -> dict:
        return {
            "address": self.address,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "total_deployments": self.total_deployments,
            "deployed_contracts": self.deployed_contracts,
            "funded_by": self.funded_by,
            "partial": self.partial,
        }


@dataclass
class ContractFacts:
    """Raw facts pulled from the chain, before any interpretation."""

    address: str
    chain: str
    verified: bool = False
    name: str = ""
    compiler: str = ""
    license: str = ""
    is_proxy: bool = False
    implementation: str = ""
    source_code: str = ""
    abi: str = ""
    creator: str = ""
    creation_tx: str = ""
    created_at: datetime | None = None
    owner: str | None = None
    total_supply: str | None = None
    token_name: str = ""
    token_symbol: str = ""
    decimals: int | None = None

    @property
    def age_days(self) -> float | None:
        if self.created_at is None:
            return None
        from datetime import timezone

        return (datetime.now(timezone.utc) - self.created_at).total_seconds() / 86400

    @property
    def ownership_renounced(self) -> bool | None:
        """True when owner() is the zero address. None when it could not be read."""
        if self.owner is None:
            return None
        return int(self.owner, 16) == 0 if self.owner.startswith("0x") else False


@dataclass
class ContractReport:
    """The full result of researching one contract address."""

    address: str
    chain: str
    facts: ContractFacts
    findings: list[Finding] = field(default_factory=list)
    deployer: DeployerProfile = field(default_factory=DeployerProfile)
    links: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    checked_at: datetime | None = None

    @property
    def risk_score(self) -> int:
        """0–100, higher is worse. A heuristic summary, not a verdict."""
        return min(100, sum(f.severity.weight for f in self.findings))

    @property
    def risk_band(self) -> str:
        score = self.risk_score
        if score >= 60:
            return "severe"
        if score >= 35:
            return "elevated"
        if score >= 15:
            return "moderate"
        return "low"

    def by_severity(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (f.severity.rank, f.title))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for finding in self.findings:
            out[finding.severity.value] = out.get(finding.severity.value, 0) + 1
        return out

    def as_dict(self) -> dict:
        return {
            "address": self.address,
            "chain": self.chain,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "counts": self.counts(),
            "facts": {
                "verified": self.facts.verified,
                "name": self.facts.name,
                "compiler": self.facts.compiler,
                "license": self.facts.license,
                "is_proxy": self.facts.is_proxy,
                "implementation": self.facts.implementation,
                "creator": self.facts.creator,
                "creation_tx": self.facts.creation_tx,
                "created_at": self.facts.created_at.isoformat() if self.facts.created_at else None,
                "age_days": self.facts.age_days,
                "owner": self.facts.owner,
                "ownership_renounced": self.facts.ownership_renounced,
                "token_name": self.facts.token_name,
                "token_symbol": self.facts.token_symbol,
                "total_supply": self.facts.total_supply,
                "decimals": self.facts.decimals,
            },
            "findings": [f.as_dict() for f in self.by_severity()],
            "deployer": self.deployer.as_dict(),
            "links": self.links,
            "errors": self.errors,
        }
