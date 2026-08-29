"""Dashboard API: correct responses, safe failures, and no path to a real order."""

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tradingbot.config import from_dict
from tradingbot.web.server import make_server


@pytest.fixture(scope="module")
def server():
    config = from_dict({"symbols": ["BTC/USDT"], "timeframe": "1h"})
    httpd = make_server(config, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(base, path):
    with urlopen(f"{base}{path}", timeout=30) as response:
        return response.status, json.loads(response.read())


def post(base, path, payload):
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return response.status, json.loads(response.read())


def expect_error(fn, *args):
    with pytest.raises(HTTPError) as exc:
        fn(*args)
    return exc.value.code, json.loads(exc.value.read())


# ------------------------------------------------------------------ static
def test_the_dashboard_page_is_served(server):
    with urlopen(f"{server}/", timeout=10) as response:
        body = response.read().decode()
    assert response.status == 200
    assert "CBot" in body


def test_static_assets_are_served(server):
    for path, marker in (("/styles.css", "--accent"), ("/app.js", "drawChart")):
        with urlopen(f"{server}{path}", timeout=10) as response:
            assert marker in response.read().decode()


@pytest.mark.parametrize(
    "path",
    [
        "/../README.md",
        "/../../etc/passwd",
        "/%2e%2e%2fREADME.md",
        "//etc/passwd",
        "/../config/config.example.yaml",
    ],
)
def test_paths_outside_the_web_root_are_refused(server, path):
    status, payload = expect_error(get, server, path)
    assert status == 404
    assert "error" in payload


# --------------------------------------------------------------------- api
def test_strategies_endpoint_lists_the_real_strategies(server):
    status, payload = get(server, "/api/strategies")
    names = [s["name"] for s in payload["strategies"]]
    assert status == 200
    assert {"sma_cross", "rsi_reversion", "breakout"} <= set(names)
    assert all(not name.startswith("_") for name in names)  # no test-only strategies


def test_each_strategy_reports_its_parameters(server):
    _, payload = get(server, "/api/strategies")
    sma = next(s for s in payload["strategies"] if s["name"] == "sma_cross")
    assert {p["name"] for p in sma["params"]} >= {"fast_period", "slow_period"}
    assert sma["description"]


def test_config_endpoint_never_exposes_a_secret(server):
    status, payload = get(server, "/api/config")
    assert status == 200
    flat = json.dumps(payload).lower()
    for forbidden in ("apikey", "api_key", "secret", "password"):
        assert forbidden not in flat


def test_status_endpoint_reports_no_state_cleanly(server):
    status, payload = get(server, "/api/status")
    assert status == 200
    assert payload["running"] is False
    assert payload["positions"] == []


def test_unknown_endpoints_return_404(server):
    status, _ = expect_error(get, server, "/api/nope")
    assert status == 404


# ---------------------------------------------------------------- backtest
def test_a_backtest_returns_metrics_a_curve_and_trades(server):
    status, payload = post(
        server,
        "/api/backtest",
        {"strategy": "sma_cross", "synthetic": True, "bars": 1200,
         "params": {"fast_period": 10, "slow_period": 30}},
    )
    assert status == 200
    assert payload["metrics"]["total_trades"] >= 0
    assert len(payload["equity_curve"]) == 1200
    assert payload["synthetic"] is True
    assert "fast_period=10" in payload["strategy"]


def test_backtest_trades_carry_the_fields_the_ui_renders(server):
    _, payload = post(
        server, "/api/backtest",
        {"strategy": "breakout", "synthetic": True, "bars": 1500,
         "params": {"entry_period": 10, "exit_period": 5}},
    )
    assert payload["trades"], "expected the breakout strategy to trade"
    required = {"opened_at", "closed_at", "side", "entry_price", "exit_price",
                "net_pnl", "return_pct", "reason"}
    assert required <= set(payload["trades"][0])


def test_risk_overrides_from_the_ui_are_applied(server):
    small = post(server, "/api/backtest", {
        "strategy": "sma_cross", "synthetic": True, "bars": 1500, "seed": 3,
        "risk": {"risk_per_trade": 0.001},
    })[1]
    large = post(server, "/api/backtest", {
        "strategy": "sma_cross", "synthetic": True, "bars": 1500, "seed": 3,
        "risk": {"risk_per_trade": 0.02},
    })[1]
    # A bigger risk budget must move equity further from its starting point.
    assert abs(large["metrics"]["total_return_pct"]) > abs(small["metrics"]["total_return_pct"])


def test_an_unknown_strategy_is_a_clean_error(server):
    status, payload = expect_error(post, server, "/api/backtest", {"strategy": "nope"})
    assert status == 400
    assert "unknown strategy" in payload["error"]
    assert not payload["error"].startswith('"')  # KeyError repr quotes stripped


def test_an_unknown_parameter_is_a_clean_error(server):
    status, payload = expect_error(
        post, server, "/api/backtest",
        {"strategy": "sma_cross", "synthetic": True, "params": {"bogus": 1}},
    )
    assert status == 400
    assert "unknown parameter" in payload["error"]


def test_an_invalid_parameter_combination_is_a_clean_error(server):
    status, payload = expect_error(
        post, server, "/api/backtest",
        {"strategy": "sma_cross", "synthetic": True,
         "params": {"fast_period": 50, "slow_period": 10}},
    )
    assert status == 400
    assert "fast_period" in payload["error"]


def test_missing_cached_data_explains_how_to_get_it(server):
    status, payload = expect_error(
        post, server, "/api/backtest", {"symbol": "NOPE/USDT", "synthetic": False}
    )
    assert status == 400
    assert "fetch" in payload["error"]


def test_an_absurd_bar_count_is_rejected(server):
    status, payload = expect_error(
        post, server, "/api/backtest",
        {"strategy": "sma_cross", "synthetic": True, "bars": 10_000_000},
    )
    assert status == 400
    assert "bars" in payload["error"]


def test_malformed_json_is_rejected_without_a_traceback(server):
    request = Request(
        f"{server}/api/backtest", data=b"{not json",
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with pytest.raises(HTTPError) as exc:
        urlopen(request, timeout=10)
    assert exc.value.code == 400
    assert "invalid JSON" in json.loads(exc.value.read())["error"]


def test_an_invalid_risk_setting_is_rejected(server):
    status, payload = expect_error(
        post, server, "/api/backtest",
        {"strategy": "sma_cross", "synthetic": True, "risk": {"risk_per_trade": 0.9}},
    )
    assert status == 400
    assert "risk_per_trade" in payload["error"]


# ------------------------------------------------------------------ safety
def test_the_api_offers_no_way_to_place_an_order(server):
    """The dashboard must not be able to trade — that stays on the CLI."""
    for path in ("/api/live", "/api/order", "/api/trade", "/api/start", "/api/paper"):
        with pytest.raises(HTTPError) as exc:
            post(server, path, {})
        assert exc.value.code == 404


def test_the_server_source_contains_no_order_submission():
    from pathlib import Path

    from tradingbot.web import server as module

    source = Path(module.__file__).read_text()
    assert "submit(" not in source
    assert "CcxtBroker" not in source


# ---------------------------------------------------------------- research
def test_the_chain_list_is_served(server):
    status, payload = get(server, "/api/chains")
    assert status == 200
    assert "ethereum" in payload["chains"]
    assert "configured" in payload


def test_a_malformed_contract_address_is_rejected(server):
    status, payload = expect_error(post, server, "/api/research", {"address": "0xnope"})
    assert status == 400
    assert "contract address" in payload["error"]


def test_an_unknown_chain_is_rejected(server):
    status, payload = expect_error(
        post, server, "/api/research",
        {"address": "0x" + "ab" * 20, "chain": "dogechain"},
    )
    assert status == 400
    assert "unsupported chain" in payload["error"]


def test_a_missing_api_key_is_reported_as_a_setup_problem(server, monkeypatch):
    import os

    if os.environ.get("ETHERSCAN_API_KEY"):
        pytest.skip("a real API key is configured in this environment")
    status, payload = expect_error(
        post, server, "/api/research", {"address": "0x" + "ab" * 20}
    )
    # 503, not 400: the browser's request was fine, the server is not set up.
    assert status == 503
    assert "etherscan.io/apis" in payload["error"]


def test_the_research_endpoint_cannot_write_anything():
    """Research is read-only: no order path, no state mutation."""
    from pathlib import Path

    from tradingbot.web import server as module

    source = Path(module.__file__).read_text()
    research = source[source.index("_run_research") : source.index("_load_candles")]
    for forbidden in ("save_state", "submit(", "create_order", "open("):
        assert forbidden not in research
