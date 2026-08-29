"""Contract research: the checks, the evidence, and the honesty boundaries."""

from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.research import (
    AuthError,
    ContractResearcher,
    EtherscanSource,
    Severity,
    SourceError,
    is_address,
    normalise_chain,
)
from tradingbot.research.heuristics import strip_noise
from tradingbot.research.sources import (
    ZERO_ADDRESS,
    decode_address,
    decode_string,
    decode_uint,
)

from .fake_chain import CLEAN_SOURCE, RUGGY_SOURCE, FakeChainSource, renounced_source

ADDRESS = "0x" + "ab" * 20


def review(**kwargs):
    return ContractResearcher("ethereum", source=FakeChainSource(**kwargs)).review(ADDRESS)


def ids(report):
    return {f.id for f in report.findings}


# ------------------------------------------------------------- validation
@pytest.mark.parametrize("value", ["0x" + "a" * 40, "0x" + "A" * 40, "0x" + "0" * 40])
def test_valid_addresses_are_accepted(value):
    assert is_address(value)


@pytest.mark.parametrize(
    "value", ["", "0x", "0x123", "a" * 42, "0x" + "z" * 40, "0x" + "a" * 41, None, 42]
)
def test_invalid_addresses_are_rejected(value):
    assert not is_address(value)


def test_reviewing_a_malformed_address_raises():
    with pytest.raises(ValueError, match="not a valid contract address"):
        ContractResearcher("ethereum", source=FakeChainSource()).review("nonsense")


@pytest.mark.parametrize(
    "alias,expected",
    [("eth", "ethereum"), ("ETH", "ethereum"), ("bnb", "bsc"), ("matic", "polygon"),
     ("arb", "arbitrum"), ("base", "base")],
)
def test_chain_aliases_resolve(alias, expected):
    assert normalise_chain(alias) == expected


def test_an_unknown_chain_is_rejected():
    with pytest.raises(SourceError, match="unsupported chain"):
        normalise_chain("dogechain")


# --------------------------------------------------------------- decoding
def test_decoders_handle_abi_encoded_values():
    assert decode_address("0x" + "0" * 24 + "cd" * 20) == "0x" + "cd" * 20
    assert decode_uint("0x" + format(18, "064x")) == 18
    body = b"USDC".hex().ljust(64, "0")
    word = "0x" + format(32, "064x") + format(4, "064x") + body
    assert decode_string(word) == "USDC"


def test_decoders_return_none_for_empty_results():
    assert decode_address(None) is None
    assert decode_address("0x") is None
    assert decode_uint(None) is None
    assert decode_string(None) == ""


# ------------------------------------------------------------- heuristics
def test_comments_and_strings_do_not_trigger_findings():
    """A mentioned mint in a comment is not a mint function."""
    source = '''
    contract A {
        // function mint(address a) external {}
        /* function blacklist() {} */
        string public note = "this contract can mint tokens";
    }
    '''
    stripped = strip_noise(source)
    assert "mint" not in stripped.lower() or "function mint" not in stripped
    report = ContractResearcher("ethereum", source=FakeChainSource(source=source)).review(ADDRESS)
    assert "mint" not in ids(report)
    assert "blacklist" not in ids(report)


def test_a_dangerous_contract_is_flagged_across_the_board():
    report = review()
    assert {"mint", "blacklist", "fee_setter", "ownership_active"} <= ids(report)
    assert report.risk_band == "severe"


def test_a_clean_renounced_contract_scores_low():
    report = ContractResearcher("ethereum", source=renounced_source()).review(ADDRESS)
    assert "ownership_renounced" in ids(report)
    assert "mint_and_owner" not in ids(report)
    assert report.risk_band == "low"


def test_every_finding_cites_its_evidence():
    """A finding without evidence is an opinion, not a check."""
    for report in (review(), ContractResearcher("ethereum", source=renounced_source()).review(ADDRESS)):
        for finding in report.findings:
            assert finding.evidence, f"{finding.id} has no evidence"
            assert finding.detail


def test_an_unverified_contract_is_critical_and_skips_source_checks():
    report = review(verified=False)
    assert "unverified" in ids(report)
    unverified = next(f for f in report.findings if f.id == "unverified")
    assert unverified.severity is Severity.CRITICAL
    # With no source there is nothing to pattern-match, so no source findings.
    assert "mint" not in ids(report)


def test_mint_plus_a_live_owner_escalates_to_critical():
    report = review()
    combo = next(f for f in report.findings if f.id == "mint_and_owner")
    assert combo.severity is Severity.CRITICAL


def test_mint_without_an_owner_does_not_escalate():
    report = review(owner=ZERO_ADDRESS)
    assert "mint" in ids(report)
    assert "mint_and_owner" not in ids(report)


def test_blacklist_plus_a_live_owner_is_called_a_honeypot_risk():
    report = review()
    combo = next(f for f in report.findings if f.id == "blacklist_and_owner")
    assert combo.severity is Severity.CRITICAL
    assert "sell" in combo.detail.lower()


def test_a_proxy_is_flagged_as_upgradeable():
    report = review(proxy=True, implementation="0x" + "99" * 20)
    assert "proxy" in ids(report)
    assert "upgradeable_and_owner" in ids(report)


def test_a_brand_new_contract_is_flagged():
    assert "very_new" in ids(review(created_days_ago=1.0))
    assert "new" in ids(review(created_days_ago=20.0))
    old = review(created_days_ago=500.0)
    assert "very_new" not in ids(old) and "new" not in ids(old)


# ---------------------------------------------------------------- deployer
def test_the_deployer_address_is_reported():
    report = review()
    assert report.deployer.address == "0x" + "11" * 20


def test_past_projects_are_listed():
    others = [
        {"address": "0x" + "cc" * 20, "tx_hash": "0x1", "timestamp": None, "succeeded": True},
        {"address": "0x" + "dd" * 20, "tx_hash": "0x2", "timestamp": None, "succeeded": True},
    ]
    report = review(deployments=others)
    assert "prior_deployments" in ids(report)
    finding = next(f for f in report.findings if f.id == "prior_deployments")
    assert "2 other contracts" in finding.title


def test_the_contract_under_review_is_not_counted_as_a_past_project():
    report = review(deployments=[
        {"address": ADDRESS, "tx_hash": "0x1", "timestamp": None, "succeeded": True}
    ])
    assert "first_deployment" in ids(report)
    assert "prior_deployments" not in ids(report)


def test_a_deployer_with_no_history_is_flagged():
    assert "first_deployment" in ids(review(deployments=[]))


def test_a_new_deployer_address_is_flagged():
    assert "new_deployer" in ids(review(deployer_first_seen_days=3.0))
    assert "new_deployer" not in ids(review(deployer_first_seen_days=900.0))


def test_a_truncated_deployer_history_is_marked_partial():
    report = review(deployments=[{"address": "0x" + "cc" * 20, "tx_hash": "0x1",
                                  "timestamp": None, "succeeded": True}], truncated=True)
    assert report.deployer.partial is True


# ------------------------------------------------------------- honesty
def test_the_report_never_claims_to_know_who_the_developers_are():
    """Identity is off-chain. The tool must say so rather than guess."""
    report = review()
    note = next(f for f in report.findings if f.id == "identity_unknown")
    assert "off-chain" in note.detail
    assert "guessing" in note.detail
    # And it must never emit a doxxed/anonymous verdict anywhere.
    text = " ".join(f"{f.title} {f.detail}" for f in report.findings).lower()
    assert "developers are anonymous" not in text
    assert "team is doxxed" not in text


def test_research_links_point_at_the_right_explorer():
    report = review()
    assert report.links["contract"].startswith("https://etherscan.io/address/")
    assert report.links["deployer"].endswith(report.deployer.address)

    bsc = ContractResearcher("bsc", source=FakeChainSource()).review(ADDRESS)
    assert "bscscan.com" in bsc.links["contract"]


def test_the_report_serialises_for_the_api():
    payload = review().as_dict()
    assert payload["risk_score"] > 0
    assert payload["findings"] and payload["deployer"]["address"]
    assert all({"id", "title", "severity", "detail"} <= set(f) for f in payload["findings"])


# ------------------------------------------------------- partial failures
def test_a_failed_fetch_degrades_instead_of_crashing():
    report = review(fail={"deployments_by"})
    assert report.errors
    assert report.findings  # the rest of the review still ran


def test_missing_creation_data_still_produces_a_report():
    report = review(fail={"creation"})
    assert report.findings
    assert any("deployment details" in e for e in report.errors)


def test_an_unconfigured_source_fails_fast_with_instructions(monkeypatch):
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    researcher = ContractResearcher("ethereum", source=EtherscanSource("ethereum"))
    with pytest.raises(AuthError, match="etherscan.io/apis"):
        researcher.review(ADDRESS)


def test_an_auth_error_is_never_swallowed_as_a_partial_failure():
    """A rejected key is fixable, so it must surface rather than empty the report."""

    class RejectingSource(FakeChainSource):
        def source_code(self, address):
            raise AuthError("the explorer rejected the API key")

    with pytest.raises(AuthError):
        ContractResearcher("ethereum", source=RejectingSource()).review(ADDRESS)


# ------------------------------------------------------------- scoring
def test_the_risk_score_is_bounded():
    assert 0 <= review().risk_score <= 100
    assert 0 <= ContractResearcher("ethereum", source=renounced_source()).review(ADDRESS).risk_score <= 100


def test_a_worse_contract_scores_higher_than_a_cleaner_one():
    ruggy = review().risk_score
    clean = ContractResearcher("ethereum", source=renounced_source()).review(ADDRESS).risk_score
    assert ruggy > clean


def test_good_findings_do_not_add_to_the_risk_score():
    assert Severity.GOOD.weight == 0
    assert Severity.INFO.weight == 0
