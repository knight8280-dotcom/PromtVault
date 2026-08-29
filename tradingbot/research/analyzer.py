"""Orchestrates a contract review: fetch facts, run checks, assemble a report."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import heuristics
from .models import ContractFacts, ContractReport, DeployerProfile, Finding, Severity
from .sources import (
    CHAINS,
    AuthError,
    SELECTORS,
    ChainSource,
    EtherscanSource,
    SourceError,
    decode_address,
    decode_string,
    decode_uint,
    is_address,
    normalise_chain,
)

log = logging.getLogger(__name__)


class ContractResearcher:
    """Builds a ContractReport from public chain data.

    Every fetch is allowed to fail independently: a missing piece is recorded in
    `report.errors` and the rest of the review still runs. A partial report with
    honest gaps beats no report.
    """

    def __init__(self, chain: str = "ethereum", source: ChainSource | None = None) -> None:
        self.chain = normalise_chain(chain)
        self.source = source or EtherscanSource(self.chain)
        self.explorer = CHAINS[self.chain]["explorer"]

    # ------------------------------------------------------------------
    def review(self, address: str, *, deployer_limit: int = 25) -> ContractReport:
        address = (address or "").strip()
        if not is_address(address):
            raise ValueError(
                f"{address!r} is not a valid contract address — expected 0x followed "
                f"by 40 hex characters"
            )

        # Fail fast rather than returning a report that is empty for a fixable
        # reason: an unconfigured source produces nothing but a wall of errors.
        if getattr(self.source, "configured", True) is False:
            raise AuthError(
                "a free Etherscan API key is required to look up contracts. Get one at "
                "https://etherscan.io/apis and set it: export ETHERSCAN_API_KEY=your_key "
                "(one key covers every supported chain)."
            )

        facts = ContractFacts(address=address, chain=self.chain)
        report = ContractReport(
            address=address,
            chain=self.chain,
            facts=facts,
            checked_at=datetime.now(timezone.utc),
        )

        self._load_source(facts, report)
        self._load_creation(facts, report)
        self._load_token(facts, report)
        self._load_owner(facts, report)
        deployer = self._load_deployer(facts, report, deployer_limit)
        report.deployer = deployer

        report.links = self._links(address, facts, deployer)

        report.findings = [
            *heuristics.analyse_source(facts),
            *heuristics.analyse_ownership(facts),
            *heuristics.analyse_deployer(deployer, address),
            heuristics.identity_note(deployer, report.links),
        ]
        self._add_combination_findings(report, facts)
        return report

    # ------------------------------------------------------------------
    def _load_source(self, facts: ContractFacts, report: ContractReport) -> None:
        try:
            data = self.source.source_code(facts.address)
        except AuthError:
            raise
        except SourceError as exc:
            report.errors.append(f"source code unavailable: {exc}")
            return

        source = data.get("SourceCode") or ""
        facts.verified = bool(source)
        facts.source_code = source
        facts.name = data.get("ContractName") or ""
        facts.compiler = data.get("CompilerVersion") or ""
        facts.license = data.get("LicenseType") or ""
        facts.abi = data.get("ABI") or ""
        facts.is_proxy = str(data.get("Proxy", "0")) == "1"
        facts.implementation = data.get("Implementation") or ""

    def _load_creation(self, facts: ContractFacts, report: ContractReport) -> None:
        try:
            data = self.source.creation(facts.address)
        except AuthError:
            raise
        except SourceError as exc:
            report.errors.append(f"deployment details unavailable: {exc}")
            return

        facts.creator = data.get("contractCreator") or ""
        facts.creation_tx = data.get("txHash") or ""
        stamp = data.get("timestamp") or data.get("timeStamp")
        if stamp:
            try:
                facts.created_at = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
            except (TypeError, ValueError):
                pass

    def _load_token(self, facts: ContractFacts, report: ContractReport) -> None:
        """Read ERC-20 metadata directly, rather than trusting a listing."""
        try:
            facts.token_name = decode_string(self.source.call(facts.address, SELECTORS["name"]))
            facts.token_symbol = decode_string(self.source.call(facts.address, SELECTORS["symbol"]))
            facts.decimals = decode_uint(self.source.call(facts.address, SELECTORS["decimals"]))
            supply = decode_uint(self.source.call(facts.address, SELECTORS["totalSupply"]))
            facts.total_supply = str(supply) if supply is not None else None
        except AuthError:
            raise
        except SourceError as exc:
            report.errors.append(f"token metadata unavailable: {exc}")

    def _load_owner(self, facts: ContractFacts, report: ContractReport) -> None:
        try:
            raw = self.source.call(facts.address, SELECTORS["owner"])
            if raw is None:
                raw = self.source.call(facts.address, SELECTORS["getOwner"])
        except AuthError:
            raise
        except SourceError as exc:
            report.errors.append(f"owner could not be read: {exc}")
            return
        facts.owner = decode_address(raw)

    def _load_deployer(
        self, facts: ContractFacts, report: ContractReport, limit: int
    ) -> DeployerProfile:
        profile = DeployerProfile(address=facts.creator)
        if not facts.creator:
            return profile

        try:
            deployments, truncated = self.source.deployments_by(facts.creator, limit=limit)
            profile.deployed_contracts = deployments
            profile.total_deployments = len(deployments)
            profile.partial = truncated
        except AuthError:
            raise
        except SourceError as exc:
            report.errors.append(f"deployer history unavailable: {exc}")

        try:
            first_seen, funder = self.source.first_activity(facts.creator)
            profile.first_seen = first_seen
            profile.funded_by = funder
        except AuthError:
            raise
        except SourceError as exc:
            report.errors.append(f"deployer age unavailable: {exc}")

        return profile

    # ------------------------------------------------------------------
    def _add_combination_findings(self, report: ContractReport, facts: ContractFacts) -> None:
        """Some risks only exist when two capabilities are present together."""
        present = {f.id for f in report.findings}
        owner_active = "ownership_active" in present

        if owner_active and "mint" in present:
            report.findings.append(
                Finding(
                    "mint_and_owner", "An active owner can mint new tokens",
                    Severity.CRITICAL,
                    "Both a mint function and a live owner are present. Whoever holds "
                    "the owner key can create tokens at will and sell them into your "
                    "liquidity. This combination is the classic rug pull.",
                    evidence=f"owner {facts.owner} with a reachable mint function",
                )
            )

        if owner_active and "blacklist" in present:
            report.findings.append(
                Finding(
                    "blacklist_and_owner", "An active owner can block your address",
                    Severity.CRITICAL,
                    "A live owner combined with address blocking means your ability to "
                    "sell can be revoked after you buy. This is how a honeypot works.",
                    evidence=f"owner {facts.owner} with a reachable blocking function",
                )
            )

        if facts.is_proxy and owner_active:
            report.findings.append(
                Finding(
                    "upgradeable_and_owner", "An active owner can replace the contract logic",
                    Severity.HIGH,
                    "An upgradeable proxy with a live owner means every guarantee in "
                    "today's source can be removed in one transaction.",
                    evidence=f"proxy implementation {facts.implementation or 'unknown'}",
                )
            )

    def _links(self, address: str, facts: ContractFacts, deployer: DeployerProfile) -> dict[str, str]:
        """Where to continue the research by hand."""
        links = {
            "contract": f"{self.explorer}/address/{address}",
            "source": f"{self.explorer}/address/{address}#code",
            "holders": f"{self.explorer}/token/{address}#balances",
            "transfers": f"{self.explorer}/token/{address}",
        }
        if deployer.address:
            links["deployer"] = f"{self.explorer}/address/{deployer.address}"
        if facts.creation_tx:
            links["deployment_tx"] = f"{self.explorer}/tx/{facts.creation_tx}"
        # Third-party checks worth running alongside this one.
        links["dexscreener"] = f"https://dexscreener.com/search?q={address}"
        links["honeypot_check"] = f"https://honeypot.is/?address={address}"
        return links


def review_contract(address: str, chain: str = "ethereum", source=None) -> ContractReport:
    """Convenience wrapper for a single review."""
    return ContractResearcher(chain, source=source).review(address)
