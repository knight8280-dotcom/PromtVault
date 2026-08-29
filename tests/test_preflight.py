"""Pre-flight: catch a broken live setup on the ground, not in the market."""

import pytest

from tradingbot.config import from_dict
from tradingbot.preflight import Status, run_preflight

from . import fake_ccxt


def config(**overrides):
    base = {
        "symbols": ["BTC/USDT"],
        "execution": {"mode": "live", "confirm_live": True, "min_order_notional": 10.0},
        "exchange": {"testnet": True},
    }
    for key, value in overrides.items():
        if isinstance(value, dict):
            base.setdefault(key, {}).update(value)
        else:
            base[key] = value
    return from_dict(base)


def broker_for(monkeypatch, **attrs):
    fake_ccxt.install(monkeypatch, **attrs)
    from tradingbot.exchange.ccxt_adapter import CcxtBroker

    def factory(cfg):
        return CcxtBroker(cfg.exchange, allow_trading=True)

    return factory


def statuses(report):
    return {c.name: c.status for c in report.checks}


def with_keys(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "abcd1234")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "secret9876")


# ----------------------------------------------------------- credentials
def test_missing_credentials_fail_with_a_fix(monkeypatch):
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("EXCHANGE_API_SECRET", raising=False)
    report = run_preflight(config())
    check = next(c for c in report.checks if c.name == "API credentials")
    assert check.status is Status.FAIL
    assert "export" in check.fix
    assert not report.ready


def test_a_seed_phrase_pasted_as_an_api_key_is_caught(monkeypatch):
    """CBot never uses a wallet seed phrase; pasting one must fail loudly."""
    monkeypatch.setenv("EXCHANGE_API_KEY", " ".join(["word"] * 12))
    monkeypatch.setenv("EXCHANGE_API_SECRET", "x")
    report = run_preflight(config())
    check = next(c for c in report.checks if c.name == "Credential type")
    assert check.status is Status.FAIL
    assert "seed phrase" in check.message
    assert "drain" in check.fix


def test_the_connection_is_skipped_when_credentials_are_missing(monkeypatch):
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("EXCHANGE_API_SECRET", raising=False)
    report = run_preflight(config())
    assert statuses(report)["Exchange connection"] is Status.SKIP


# ------------------------------------------------------------------ locks
def test_production_is_warned_about(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(config(exchange={"testnet": False}),
                           broker_factory=broker_for(monkeypatch))
    venue = next(c for c in report.checks if c.name == "Venue")
    assert venue.status is Status.WARN
    assert "real funds" in venue.message


def test_the_testnet_passes_without_a_warning(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(config(), broker_factory=broker_for(monkeypatch))
    assert statuses(report)["Venue"] is Status.PASS


def test_a_missing_live_confirmation_is_a_warning_not_a_failure(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(config(execution={"confirm_live": False}),
                           broker_factory=broker_for(monkeypatch))
    assert statuses(report)["Live confirmation"] is Status.WARN
    assert report.ready  # it blocks live trading, but the setup is not broken


# ------------------------------------------------------------------- risk
def test_aggressive_risk_is_flagged(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(config(risk={"risk_per_trade": 0.05}),
                           broker_factory=broker_for(monkeypatch))
    assert statuses(report)["Risk per trade"] is Status.WARN


def test_enabling_shorts_is_flagged(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(config(risk={"allow_shorts": True}),
                           broker_factory=broker_for(monkeypatch))
    check = next(c for c in report.checks if c.name == "Short selling")
    assert check.status is Status.WARN
    assert "unbounded" in check.message


# ---------------------------------------------------------------- account
def test_a_healthy_account_passes_every_check(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(config(), broker_factory=broker_for(monkeypatch))
    assert report.ready
    assert statuses(report)["Account access"] is Status.PASS
    assert statuses(report)["Symbols"] is Status.PASS


def test_an_empty_account_fails(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(
        config(), broker_factory=broker_for(monkeypatch, balance={"free": {"USDT": 0.0}})
    )
    check = next(c for c in report.checks if c.name == "Tradable balance")
    assert check.status is Status.FAIL
    assert not report.ready


def test_an_account_too_small_to_clear_the_minimum_is_warned(monkeypatch):
    with_keys(monkeypatch)
    # 20 USDT at 20% max position = a 4 USDT position, under the 10 minimum.
    report = run_preflight(
        config(), broker_factory=broker_for(monkeypatch, balance={"free": {"USDT": 20.0}})
    )
    check = next(c for c in report.checks if c.name == "Tradable balance")
    assert check.status is Status.WARN
    assert "minimum order size" in check.message


def test_an_unreadable_balance_fails(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(
        config(),
        broker_factory=broker_for(monkeypatch, failures=[fake_ccxt.BaseError("no permission")]),
    )
    assert statuses(report)["Account access"] is Status.FAIL
    assert not report.ready


# ---------------------------------------------------------------- symbols
def test_an_untradable_symbol_fails(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(
        config(symbols=["DOGE/USDT"]),
        broker_factory=broker_for(monkeypatch, markets={"BTC/USDT": {}}),
    )
    check = next(c for c in report.checks if c.name == "Symbols")
    assert check.status is Status.FAIL
    assert "DOGE/USDT" in check.message


def test_a_venue_minimum_above_our_own_is_warned(monkeypatch):
    with_keys(monkeypatch)
    report = run_preflight(
        config(),
        broker_factory=broker_for(
            monkeypatch, markets={"BTC/USDT": {"limits": {"cost": {"min": 50.0}}}}
        ),
    )
    check = next(c for c in report.checks if "Minimum size" in c.name)
    assert check.status is Status.WARN
    assert "50" in check.fix


# -------------------------------------------------------------- read-only
def test_preflight_never_places_an_order(monkeypatch):
    """It is a pre-flight check, not a trade."""
    with_keys(monkeypatch)
    factory = broker_for(monkeypatch)
    holder = {}

    def recording(cfg):
        holder["broker"] = factory(cfg)
        return holder["broker"]

    run_preflight(config(), broker_factory=recording)
    assert not [c for c in holder["broker"].client.calls if c[0] == "create_order"]
