"""Source-code and on-chain heuristics.

Every check produces a Finding with the evidence that triggered it — a matched
source line, an address, a date. A check that cannot cite what it saw is not a
check, it is a guess, and guesses do not belong in a due-diligence tool.

These detect *capabilities*, not intent. A mint function is how a legitimate
stablecoin works and also how a rug pull works; the tool tells you the power
exists and who holds it. Judging it is your job.
"""

from __future__ import annotations

import re

from .models import ContractFacts, DeployerProfile, Finding, Severity

# Comments and strings are stripped before matching, so a pattern hit is real code.
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def strip_noise(source: str) -> str:
    """Remove comments and string literals so matches reflect executable code."""
    source = _BLOCK_COMMENT.sub(" ", source)
    source = _LINE_COMMENT.sub(" ", source)
    return _STRING.sub('""', source)


def _find(source: str, pattern: str) -> str:
    """Return the first matching line, trimmed, as evidence."""
    match = re.search(pattern, source, re.IGNORECASE)
    if not match:
        return ""
    start = source.rfind("\n", 0, match.start()) + 1
    end = source.find("\n", match.end())
    line = source[start : end if end != -1 else len(source)].strip()
    return line[:200]


#: (id, title, regex, severity, detail). Ordered roughly worst-first.
SOURCE_PATTERNS: list[tuple[str, str, str, Severity, str]] = [
    (
        "mint", "Token supply can be increased",
        r"\bfunction\s+_?mint\w*\s*\(", Severity.HIGH,
        "A mint function lets whoever controls it create new tokens, diluting every "
        "existing holder. Check who can call it and whether that power is renounced.",
    ),
    (
        "blacklist", "Addresses can be blocked from trading",
        r"\b(blacklist|blackList|_isBlacklisted|isBot|_bots|denylist)\b", Severity.HIGH,
        "The contract can prevent specific addresses from transferring. This is the "
        "mechanism behind honeypots, where buying works but selling does not.",
    ),
    (
        "selfdestruct", "Contract can destroy itself",
        r"\bselfdestruct\s*\(|\bsuicide\s*\(", Severity.HIGH,
        "Selfdestruct removes the contract and can send its balance elsewhere.",
    ),
    (
        "pause", "Transfers can be paused",
        r"\bfunction\s+pause\w*\s*\(|\bwhenNotPaused\b|\b_paused\b", Severity.MEDIUM,
        "Transfers can be frozen. Legitimate for a regulated token, and also a way "
        "to trap holders.",
    ),
    (
        "fee_setter", "Trading fees can be changed after launch",
        r"\bfunction\s+set\w*(fee|tax)\w*\s*\(", Severity.MEDIUM,
        "The fee taken on each trade can be changed. Look for an enforced ceiling — "
        "without one, fees can be raised to effectively block selling.",
    ),
    (
        "max_tx", "Transaction and wallet caps can be changed",
        r"\bfunction\s+set\w*(maxtx|maxwallet|maxtransaction)\w*\s*\(", Severity.LOW,
        "Limits on trade and holding size can be adjusted, which can also be used to "
        "restrict selling.",
    ),
    (
        "exclude_fee", "Some addresses can be exempted from fees",
        r"\b_isExcludedFrom(Fee|Fees)\b|\bexcludeFromFee\w*\s*\(", Severity.LOW,
        "Certain addresses can trade without paying fees. Common and usually benign, "
        "but it means fees do not apply equally.",
    ),
    (
        "tx_origin", "Uses tx.origin",
        r"\btx\.origin\b", Severity.MEDIUM,
        "tx.origin is unsafe for authorisation and can often be phished.",
    ),
    (
        "delegatecall", "Uses delegatecall",
        r"\bdelegatecall\s*\(", Severity.MEDIUM,
        "delegatecall runs another contract's code with this contract's storage. "
        "Normal in proxies, dangerous when the target can be changed.",
    ),
    (
        "hidden_mint", "Balance mapping is written outside transfers",
        r"_balances\s*\[[^\]]+\]\s*=\s*(?!_balances)", Severity.MEDIUM,
        "A balance is assigned directly rather than adjusted by a transfer. This is "
        "how a hidden mint is usually written.",
    ),
]

#: Ownership patterns that are reassuring rather than alarming.
GOOD_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        "renounce_available", "Ownership can be renounced",
        r"\bfunction\s+renounceOwnership\s*\(",
        "The contract includes the standard renounce function. Whether it has "
        "actually been called is reported separately.",
    ),
    (
        "timelock", "Uses a timelock",
        r"\bTimelock\w*\b|\bMINIMUM_DELAY\b",
        "Privileged actions appear to be delayed, giving holders time to react.",
    ),
]


def analyse_source(facts: ContractFacts) -> list[Finding]:
    """Run every source pattern over a verified contract."""
    if not facts.verified:
        return [
            Finding(
                "unverified", "Source code is not published",
                Severity.CRITICAL,
                "The contract's source is not verified on the explorer, so nobody can "
                "read what it actually does. Everything below is limited to what can "
                "be seen without source. Treat an unverified token as unreviewable.",
                evidence=f"{facts.address} has no verified source on {facts.chain}",
            )
        ]

    source = strip_noise(facts.source_code)
    findings: list[Finding] = []

    for check_id, title, pattern, severity, detail in SOURCE_PATTERNS:
        evidence = _find(source, pattern)
        if evidence:
            findings.append(Finding(check_id, title, severity, detail, evidence))

    for check_id, title, pattern, detail in GOOD_PATTERNS:
        evidence = _find(source, pattern)
        if evidence:
            findings.append(Finding(check_id, title, Severity.GOOD, detail, evidence))

    findings.append(
        Finding(
            "verified", "Source code is published and verified",
            Severity.GOOD,
            "The deployed bytecode matches published source, so the contract can be "
            "read and reviewed.",
            evidence=f"{facts.name or 'contract'} compiled with {facts.compiler or 'unknown compiler'}",
        )
    )
    return findings


def analyse_ownership(facts: ContractFacts) -> list[Finding]:
    """Who holds the privileged keys, and does that still matter."""
    findings: list[Finding] = []
    renounced = facts.ownership_renounced

    if renounced is True:
        findings.append(
            Finding(
                "ownership_renounced", "Ownership has been renounced",
                Severity.GOOD,
                "owner() is the zero address, so owner-only functions can no longer be "
                "called. Note this does not disable powers held by other roles or by a "
                "proxy admin.",
                evidence=f"owner() returns {facts.owner}",
            )
        )
    elif renounced is False:
        findings.append(
            Finding(
                "ownership_active", "An owner address still controls the contract",
                Severity.MEDIUM,
                "Owner-only functions can still be called. Combined with a mint, fee or "
                "blacklist capability, this is the power that matters most.",
                evidence=f"owner() returns {facts.owner}",
            )
        )

    if facts.is_proxy:
        findings.append(
            Finding(
                "proxy", "Contract is an upgradeable proxy",
                Severity.HIGH,
                "The logic behind this address can be replaced, so a review of today's "
                "code does not describe tomorrow's. Check who controls the upgrade.",
                evidence=f"implementation: {facts.implementation or 'unknown'}",
            )
        )

    age = facts.age_days
    if age is not None and age < 7:
        findings.append(
            Finding(
                "very_new", "Contract is less than a week old",
                Severity.MEDIUM,
                "New contracts have no track record. Most rug pulls happen within days "
                "of deployment.",
                evidence=f"deployed {age:.1f} days ago",
            )
        )
    elif age is not None and age < 30:
        findings.append(
            Finding(
                "new", "Contract is less than a month old",
                Severity.LOW,
                "A short history means limited evidence either way.",
                evidence=f"deployed {age:.1f} days ago",
            )
        )

    if facts.license and facts.license.lower() not in ("none", "unlicense", ""):
        findings.append(
            Finding(
                "licensed", f"Published under {facts.license}",
                Severity.INFO,
                "The source carries a declared licence.",
                evidence=facts.license,
            )
        )
    return findings


def analyse_deployer(profile: DeployerProfile, this_address: str) -> list[Finding]:
    """What the deployer has built before.

    This is the closest the chain gets to a track record. It says nothing about
    who anyone is — only what this address has done.
    """
    findings: list[Finding] = []
    if not profile.address:
        return findings

    others = [
        d for d in profile.deployed_contracts
        if d.get("address", "").lower() != this_address.lower()
    ]

    if not others:
        findings.append(
            Finding(
                "first_deployment", "Deployer has no other contracts on this chain",
                Severity.MEDIUM,
                "This appears to be the address's only deployment here. A fresh address "
                "with no history is normal for a new team and is also what someone "
                "starting over after a failed project looks like.",
                evidence=f"{profile.address} has no other deployments found",
            )
        )
    else:
        sample = ", ".join(d["address"][:10] + "…" for d in others[:3])
        findings.append(
            Finding(
                "prior_deployments",
                f"Deployer has {len(others)} other contract{'s' if len(others) != 1 else ''} on this chain",
                Severity.INFO,
                "Review these. A history of abandoned tokens is the single most useful "
                "signal available on-chain; a history of long-lived contracts is the "
                "opposite. Each is listed below with a link.",
                evidence=f"{sample}{'…' if len(others) > 3 else ''}",
            )
        )

    if profile.first_seen is not None:
        from datetime import datetime, timezone

        age = (datetime.now(timezone.utc) - profile.first_seen).total_seconds() / 86400
        if age < 30:
            findings.append(
                Finding(
                    "new_deployer", "Deployer address is less than a month old",
                    Severity.MEDIUM,
                    "The address itself is new, so it carries no reputation. Teams "
                    "reusing a long-lived address have more to lose.",
                    evidence=f"first transaction {profile.first_seen:%Y-%m-%d} ({age:.0f} days ago)",
                )
            )
    return findings


def identity_note(profile: DeployerProfile, links: dict[str, str]) -> Finding:
    """State plainly that on-chain data cannot tell you who anyone is."""
    return Finding(
        "identity_unknown", "Team identity cannot be verified on-chain",
        Severity.INFO,
        "Whether the developers are publicly identified is an off-chain question — no "
        "amount of chain data answers it, and any tool claiming a doxxed/anonymous "
        "verdict is guessing. What is verifiable is the deployer address and what it "
        "has deployed before, both shown here. To check identity yourself, follow the "
        "research links: the project's own site and socials, whether an audit names "
        "the team, and whether the address appears in any KYC attestation.",
        evidence=f"deployer {profile.address or 'unknown'}",
    )
