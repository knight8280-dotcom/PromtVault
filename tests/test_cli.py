"""CLI behaviour, above all the guards that keep live trading from firing by accident."""

import pytest

from tradingbot.cli import _coerce, _parse_params, build_parser, main


def run(argv):
    return main(argv)


# ------------------------------------------------------------ live guards
def test_live_is_refused_without_confirm_live_in_the_config(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("execution:\n  confirm_live: false\n")
    assert run(["live", "-c", str(path), "--i-understand-the-risk"]) == 1
    assert "confirm_live" in capsys.readouterr().err


def test_live_is_refused_without_the_command_line_acknowledgement(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("execution:\n  confirm_live: true\n")
    assert run(["live", "-c", str(path)]) == 1
    assert "i-understand-the-risk" in capsys.readouterr().err


def test_live_with_real_funds_is_refused_from_a_non_interactive_shell(tmp_path, capsys, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "execution:\n  confirm_live: true\nexchange:\n  testnet: false\n"
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert run(["live", "-c", str(path), "--i-understand-the-risk"]) == 1
    assert "non-interactive" in capsys.readouterr().err


def test_the_default_config_cannot_trade_live():
    from tradingbot.config import from_dict

    assert from_dict({}).execution.confirm_live is False


# ---------------------------------------------------------------- backtest
def test_backtest_runs_on_synthetic_data(capsys):
    assert run(["backtest", "--synthetic", "--bars", "800", "--log-level", "ERROR"]) == 0
    assert "Total return" in capsys.readouterr().out


def test_backtest_writes_json_when_asked(tmp_path):
    out = tmp_path / "result.json"
    run(["backtest", "--synthetic", "--bars", "800", "--json", str(out), "--log-level", "ERROR"])
    import json

    payload = json.loads(out.read_text())
    assert "metrics" in payload and "trades" in payload


def test_backtest_writes_an_equity_curve_when_asked(tmp_path):
    out = tmp_path / "equity.csv"
    run(["backtest", "--synthetic", "--bars", "500", "--equity-csv", str(out), "--log-level", "ERROR"])
    lines = out.read_text().splitlines()
    assert lines[0] == "timestamp,equity,cash,position_value"
    assert len(lines) == 501


def test_backtest_without_cached_data_explains_the_options(capsys):
    assert run(["backtest", "-s", "DOGE/USDT", "--log-level", "ERROR"]) == 1
    assert "--synthetic" in capsys.readouterr().err


def test_strategy_parameters_can_be_overridden_on_the_command_line(capsys):
    run([
        "backtest", "--synthetic", "--bars", "600", "--strategy", "sma_cross",
        "--param", "fast_period=8", "--param", "slow_period=21", "--log-level", "ERROR",
    ])
    assert "fast_period=8" in capsys.readouterr().out


def test_an_invalid_strategy_parameter_is_reported(capsys):
    with pytest.raises(SystemExit):
        run(["backtest", "--synthetic", "--strategy", "sma_cross", "--param", "nope=1"])


def test_a_malformed_param_argument_is_reported():
    with pytest.raises(SystemExit):
        _parse_params(["no_equals_sign"])


# ----------------------------------------------------------------- parsing
@pytest.mark.parametrize(
    "raw,expected",
    [("10", 10), ("1.5", 1.5), ("true", True), ("False", False), ("none", None), ("abc", "abc")],
)
def test_param_values_are_coerced_to_sensible_types(raw, expected):
    assert _coerce(raw) == expected


def test_params_parse_into_a_mapping():
    assert _parse_params(["a=1", "b=2.5", "c=true"]) == {"a": 1, "b": 2.5, "c": True}


# ------------------------------------------------------------------- misc
def test_strategies_command_lists_every_strategy(capsys):
    assert run(["strategies"]) == 0
    out = capsys.readouterr().out
    for name in ("sma_cross", "rsi_reversion", "breakout"):
        assert name in out


def test_status_reports_when_there_is_no_saved_state(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text(f"state_dir: {tmp_path / 'state'}\n")
    assert run(["status", "-c", str(path)]) == 0
    assert "no saved state" in capsys.readouterr().out


def test_a_bad_config_file_exits_with_a_config_error(tmp_path, capsys):
    path = tmp_path / "config.yaml"
    path.write_text("timeframe: 7h\n")
    assert run(["backtest", "-c", str(path), "--synthetic"]) == 2
    assert "config error" in capsys.readouterr().err


def test_optimize_requires_a_grid(capsys):
    with pytest.raises(SystemExit):
        run(["optimize", "--synthetic", "--bars", "400"])


def test_optimize_ranks_parameter_combinations(capsys):
    code = run([
        "optimize", "--synthetic", "--bars", "800", "--strategy", "sma_cross",
        "--grid", "fast_period=5,10", "--grid", "slow_period=20,40", "--log-level", "ERROR",
    ])
    assert code == 0
    assert "Grid search" in capsys.readouterr().out


def test_a_missing_subcommand_is_an_error():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
