"""Config validation catches unsafe settings before any money is at stake."""

import pytest

from tradingbot.config import Config, ConfigError, ExchangeConfig, from_dict, load_config


def test_defaults_are_paper_mode():
    config = from_dict({})
    assert config.execution.mode == "paper"
    assert not config.is_live
    assert not config.execution.confirm_live


def test_defaults_disable_shorting_and_use_the_testnet():
    config = from_dict({})
    assert not config.risk.allow_shorts
    assert config.exchange.testnet


def test_a_single_symbol_string_is_accepted():
    assert from_dict({"symbols": "ETH/USDT"}).symbols == ["ETH/USDT"]


def test_a_malformed_symbol_is_rejected():
    with pytest.raises(ConfigError, match="BASE/QUOTE"):
        from_dict({"symbols": ["BTCUSDT"]})


def test_an_unsupported_timeframe_is_rejected():
    with pytest.raises(ConfigError, match="timeframe"):
        from_dict({"timeframe": "7h"})


def test_unknown_keys_are_rejected_rather_than_silently_ignored():
    # A typo in a risk limit must fail loudly, not leave the default in place.
    with pytest.raises(ConfigError, match="unknown key"):
        from_dict({"risk": {"risk_per_trad": 0.01}})


def test_risking_too_much_per_trade_is_rejected():
    with pytest.raises(ConfigError, match="risk_per_trade"):
        from_dict({"risk": {"risk_per_trade": 0.5}})


def test_zero_risk_per_trade_is_rejected():
    with pytest.raises(ConfigError):
        from_dict({"risk": {"risk_per_trade": 0.0}})


def test_a_position_cap_above_the_exposure_cap_is_rejected():
    with pytest.raises(ConfigError, match="max_position_pct"):
        from_dict({"risk": {"max_position_pct": 0.9, "max_total_exposure_pct": 0.5}})


def test_an_invalid_execution_mode_is_rejected():
    with pytest.raises(ConfigError, match="mode"):
        from_dict({"execution": {"mode": "yolo"}})


def test_negative_fees_are_rejected():
    with pytest.raises(ConfigError, match="fee_rate"):
        from_dict({"execution": {"fee_rate": -0.001}})


def test_credentials_come_from_the_environment_not_the_config(monkeypatch):
    monkeypatch.setenv("MY_KEY", "abc")
    monkeypatch.setenv("MY_SECRET", "xyz")
    exchange = ExchangeConfig(api_key_env="MY_KEY", api_secret_env="MY_SECRET")
    assert exchange.credentials() == {"apiKey": "abc", "secret": "xyz"}


def test_missing_credentials_yield_an_empty_mapping(monkeypatch):
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("EXCHANGE_API_SECRET", raising=False)
    monkeypatch.delenv("EXCHANGE_API_PASSWORD", raising=False)
    assert ExchangeConfig().credentials() == {}


def test_no_config_field_can_hold_a_secret():
    """Guards against someone adding an `api_key` field to the config schema."""
    from dataclasses import fields

    for cls in (Config, ExchangeConfig):
        for field in fields(cls):
            name = field.name.lower()
            assert not (name.endswith("key") or name.endswith("secret")), (
                f"{cls.__name__}.{field.name} looks like it holds a secret; "
                "secrets must come from the environment"
            )


def test_a_missing_config_file_is_reported_clearly(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_a_yaml_config_round_trips(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "symbols: [ETH/USDT]\n"
        "timeframe: 4h\n"
        "strategy:\n"
        "  name: breakout\n"
        "  params:\n"
        "    entry_period: 30\n"
        "risk:\n"
        "  risk_per_trade: 0.005\n"
    )
    config = load_config(path)
    assert config.symbols == ["ETH/USDT"]
    assert config.timeframe == "4h"
    assert config.strategy.params["entry_period"] == 30
    assert config.risk.risk_per_trade == 0.005


def test_a_non_mapping_config_file_is_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(path)
