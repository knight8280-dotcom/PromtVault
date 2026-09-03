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
    for path, marker in (("/styles.css", "--accent"), ("/js/charts.js", "equityChart")):
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
    assert "no cached data" in payload["error"]
    assert "synthetic" in payload["error"]


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


def test_no_web_module_can_submit_an_order():
    """The whole web package must have no path to placing a trade."""
    from pathlib import Path

    import tradingbot.web as package

    # Named precisely: the job runner has its own `submit`, which is not an order.
    forbidden = ("create_order", "CcxtBroker", "PaperBroker", "TradingEngine",
                 "Order(", "broker.submit")
    web_dir = Path(package.__file__).parent
    for path in sorted(web_dir.glob("*.py")):
        source = path.read_text()
        for symbol in forbidden:
            assert symbol not in source, f"{path.name} references {symbol}"


def test_the_browser_javascript_has_no_order_path():
    """Nothing in the front end should even name an order endpoint."""
    from pathlib import Path

    web = Path(__file__).resolve().parent.parent / "web"
    for path in sorted(web.rglob("*.js")):
        source = path.read_text()
        for forbidden in ("/api/order", "/api/live", "/api/trade", "createOrder"):
            assert forbidden not in source, f"{path} references {forbidden}"


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


def test_the_web_layer_never_writes_bot_state():
    """Analysis is read-only: the site reads saved state and never mutates it."""
    from pathlib import Path

    import tradingbot.web as package

    for path in sorted(Path(package.__file__).parent.glob("*.py")):
        source = path.read_text()
        assert "save_state" not in source, f"{path.name} writes bot state"


# ==================================================================
# The expanded site API
# ==================================================================
def poll_job(base, job_id, timeout=120):
    """Follow a background job to completion, the way the page does."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, job = get(base, f"/api/jobs/{job_id}")
        if job["state"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.4)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


# ------------------------------------------------------------ reference
def test_datasets_are_listed(server):
    status, payload = get(server, "/api/datasets")
    assert status == 200
    assert isinstance(payload["datasets"], list)


def test_fee_tiers_are_listed(server):
    status, payload = get(server, "/api/fee-tiers")
    assert status == 200
    keys = {t["key"] for t in payload["tiers"]}
    assert {"binance", "binance_perp", "coinbase"} <= keys
    for tier in payload["tiers"]:
        assert tier["maker"] <= tier["taker"]


def test_execution_costs_are_served(server):
    status, payload = get(server, "/api/execution")
    assert status == 200
    tier = payload["tiers"][0]
    assert tier["rows"]
    assert {"mode", "fill_rate", "effective_fee", "round_trip", "breakeven_pct"} <= set(tier["rows"][0])


def test_the_config_endpoint_reports_execution_settings(server):
    _, payload = get(server, "/api/config")
    assert "fee_tier" in payload and "prefer_maker" in payload


# -------------------------------------------------------------- regime
def test_regime_analysis_returns_a_summary_and_timeline(server):
    status, payload = post(
        server, "/api/regime", {"synthetic": True, "bars": 1500, "period": 30}
    )
    assert status == 200
    assert payload["current"]["regime"] in ("trending", "choppy", "volatile", "quiet", "unknown")
    assert payload["summary"]
    assert payload["timeline"]
    assert abs(sum(payload["summary"].values()) - 1.0) < 1e-6


def test_regime_needs_enough_bars(server):
    status, payload = expect_error(
        post, server, "/api/regime", {"synthetic": True, "bars": 100, "period": 300}
    )
    assert status == 400


# ------------------------------------------------------- backtest extras
def test_a_backtest_reports_the_benchmark_curve(server):
    _, payload = post(server, "/api/backtest", {"strategy": "sma_cross", "synthetic": True, "bars": 1200})
    assert payload["benchmark_curve"]
    assert payload["metrics"]["benchmark_return_pct"] is not None
    assert len(payload["benchmark_curve"]) == len(payload["equity_curve"])


def test_regime_gating_can_be_requested(server):
    _, payload = post(
        server, "/api/backtest",
        {"strategy": "sma_cross", "synthetic": True, "bars": 2000, "regime_gate": True},
    )
    assert "regime_gated" in payload["strategy"]
    assert "regime_blocked" in payload


def test_an_unknown_regime_mode_is_rejected(server):
    status, _ = expect_error(
        post, server, "/api/backtest",
        {"strategy": "sma_cross", "synthetic": True, "regime_gate": True, "regime_allow": "sideways"},
    )
    assert status == 400


# ------------------------------------------------------------- jobs API
def test_validate_runs_as_a_job_and_returns_four_checks(server):
    _, started = post(
        server, "/api/validate",
        {"strategy": "sma_cross", "synthetic": True, "bars": 1200,
         "params": {"fast_period": 10, "slow_period": 30}},
    )
    assert started["state"] in ("queued", "running")

    job = poll_job(server, started["id"])
    assert job["state"] == "done", job.get("error")
    result = job["result"]
    assert result["total"] == 4
    assert len(result["checks"]) == 4
    assert result["cost_curve"]
    assert 0 <= result["passed"] <= 4


def test_walkforward_runs_as_a_job(server):
    _, started = post(
        server, "/api/walkforward",
        {"strategy": "sma_cross", "grid": {"fast_period": [10, 20]},
         "synthetic": True, "bars": 2500, "train_bars": 800, "test_bars": 300},
    )
    job = poll_job(server, started["id"], timeout=240)
    assert job["state"] == "done", job.get("error")
    result = job["result"]
    assert result["windows"]
    assert "degradation" in result and "parameter_stability" in result


def test_an_oversized_grid_is_refused(server):
    _, started = post(
        server, "/api/walkforward",
        {"strategy": "sma_cross", "synthetic": True, "bars": 2500,
         "grid": {"fast_period": list(range(2, 20)), "slow_period": list(range(20, 40))}},
    )
    job = poll_job(server, started["id"])
    assert job["state"] == "failed"
    assert "too many" in job["error"]


def test_a_missing_grid_is_refused(server):
    _, started = post(server, "/api/walkforward", {"strategy": "sma_cross", "synthetic": True})
    job = poll_job(server, started["id"])
    assert job["state"] == "failed"
    assert "grid" in job["error"]


def test_a_job_can_be_cancelled_through_the_api(server):
    _, started = post(
        server, "/api/walkforward",
        {"strategy": "sma_cross", "grid": {"fast_period": [5, 10, 20], "slow_period": [30, 50, 80]},
         "synthetic": True, "bars": 6000, "train_bars": 800, "test_bars": 200},
    )
    status, payload = post(server, f"/api/jobs/{started['id']}/cancel", {})
    assert status == 200
    assert payload["cancelled"] == started["id"]

    job = poll_job(server, started["id"], timeout=120)
    assert job["state"] in ("cancelled", "done")


def test_cancelling_an_unknown_job_is_a_conflict(server):
    status, _ = expect_error(post, server, "/api/jobs/nosuchjob/cancel", {})
    assert status == 409


def test_an_unknown_job_id_is_404(server):
    status, _ = expect_error(get, server, "/api/jobs/deadbeef")
    assert status == 404


def test_jobs_are_listed(server):
    post(server, "/api/validate", {"strategy": "sma_cross", "synthetic": True, "bars": 1000})
    status, payload = get(server, "/api/jobs")
    assert status == 200
    assert payload["jobs"]
    assert {"id", "kind", "state", "progress"} <= set(payload["jobs"][0])


# ------------------------------------------------------------- static
def test_every_javascript_module_is_served(server):
    """A missing module breaks the whole site, since one import failure halts it."""
    modules = [
        "/js/main.js", "/js/api.js", "/js/router.js", "/js/ui.js",
        "/js/charts.js", "/js/format.js",
        "/js/views/overview.js", "/js/views/backtest.js", "/js/views/validate.js",
        "/js/views/walkforward.js", "/js/views/regime.js", "/js/views/carry.js",
        "/js/views/execution.js", "/js/views/contracts.js", "/js/views/status.js",
        "/js/views/data.js", "/js/views/jobs.js",
    ]
    for path in modules:
        with urlopen(f"{server}{path}", timeout=10) as response:
            assert response.status == 200, path
            assert response.headers["Content-Type"].startswith("text/javascript") or \
                   response.headers["Content-Type"].startswith("application/javascript"), path


def test_javascript_is_not_served_with_a_sniffable_type(server):
    with urlopen(f"{server}/js/main.js", timeout=10) as response:
        assert response.headers["X-Content-Type-Options"] == "nosniff"


# ==================================================================
# Listing, resuming and linking results
# ==================================================================
def test_the_job_list_carries_summaries_and_the_job_endpoint_the_result(server):
    """The list is polled every few seconds; results can be megabytes."""
    _, started = post(server, "/api/validate", {"strategy": "sma_cross", "synthetic": True, "bars": 1000})
    job = poll_job(server, started["id"])
    assert job["result"] is not None
    assert job["has_result"] is True
    assert job["label"] == "sma_cross · synthetic 1000 bars"

    _, listing = get(server, "/api/jobs")
    row = next(j for j in listing["jobs"] if j["id"] == started["id"])
    assert "result" not in row
    assert row["has_result"] is True
    assert row["label"] == job["label"]


def test_a_job_label_names_real_data_when_it_is_used(server):
    _, started = post(server, "/api/validate", {"strategy": "breakout", "symbol": "ETH/USDT", "timeframe": "4h"})
    assert started["label"] == "breakout · ETH/USDT 4h"
    poll_job(server, started["id"])  # fails cleanly: no cached data


def test_a_carry_job_label_names_the_venue(server):
    _, started = post(server, "/api/carry", {"venue": "bybit", "limit": 7})
    assert started["label"] == "bybit · top 7"
    poll_job(server, started["id"])


# ----------------------------------------------------------- headers
def test_the_page_carries_a_content_security_policy(server):
    with urlopen(f"{server}/", timeout=10) as response:
        csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp


def test_the_index_page_loads_nothing_from_another_origin():
    """The CSP forbids it, so any such tag would silently fail in the browser."""
    import re
    from pathlib import Path

    index = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text()
    for url in re.findall(r'(?:src|href)="([^"]+)"', index):
        assert not url.startswith(("http:", "https:", "//")), url


# ---------------------------------------------------------- datasets
def test_dataset_summaries_are_cached_until_the_file_changes(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from tradingbot.data import csv_store
    from tradingbot.models import Candle
    from tradingbot.web import api

    def candles(n, start=datetime(2024, 1, 1, tzinfo=timezone.utc)):
        return [
            Candle(start + timedelta(hours=i), 100.0, 101.0, 99.0, 100.0 + i, 1.0)
            for i in range(n)
        ]

    path = tmp_path / "BTC-USDT_1h.csv"
    csv_store.save(path, candles(10))
    config = from_dict({"symbols": ["BTC/USDT"], "timeframe": "1h", "data_dir": str(tmp_path)})

    first = api.describe_datasets(config)["datasets"]
    assert len(first) == 1 and first[0]["bars"] == 10

    calls = []
    real_load = csv_store.load
    monkeypatch.setattr(csv_store, "load", lambda p: calls.append(p) or real_load(p))
    assert api.describe_datasets(config)["datasets"][0]["bars"] == 10
    assert calls == [], "an unchanged file must not be re-parsed"

    # More bars written: the file's size changes and the summary follows.
    csv_store.save(path, candles(25))
    assert api.describe_datasets(config)["datasets"][0]["bars"] == 25
    assert calls == [path]


# ---------------------------------------------------------- frontend
def test_every_front_end_module_parses():
    """A syntax error in one module blanks the whole site. Node, when present,
    can parse ES modules; the server test above only proves they are served."""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    web = Path(__file__).resolve().parent.parent / "web"
    for path in sorted(web.rglob("*.js")):
        # --check parses as CommonJS unless the file is .mjs, so hand node a
        # copy under that name.
        result = subprocess.run(
            [node, "--input-type=module", "--check"],
            input=path.read_text(), capture_output=True, text=True,
        )
        assert result.returncode == 0, f"{path.name}: {result.stderr}"


def test_the_new_front_end_modules_are_served(server):
    with urlopen(f"{server}/js/setup.js", timeout=10) as response:
        assert "setupFromParams" in response.read().decode()


def test_a_job_keeps_the_request_it_was_started_with(server):
    """A page reopening a job from the list refills its form from this."""
    body = {"strategy": "sma_cross", "synthetic": True, "bars": 1000,
            "params": {"fast_period": 12, "slow_period": 40}, "fee_rate": 0.0005}
    _, started = post(server, "/api/validate", body)
    _, job = get(server, f"/api/jobs/{started['id']}")
    assert job["request"] == body

    _, listing = get(server, "/api/jobs")
    row = next(j for j in listing["jobs"] if j["id"] == started["id"])
    assert "request" not in row  # summaries stay small
    poll_job(server, started["id"])
