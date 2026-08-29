"""HTTP backend for the CBot dashboard.

Built on the standard library so the dashboard adds no dependencies. It binds to
localhost by default and is deliberately limited: it can run backtests and read
saved state, but it cannot place an order. Live trading stays on the CLI, where
the confirmation locks live — a browser tab is not somewhere a real order should
be one click away.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..backtest import Backtester
from ..config import Config, ConfigError, from_dict
from ..data import generate_synthetic, load_history
from ..research import AuthError, ContractResearcher, SourceError, is_address
from ..research.sources import CHAINS as RESEARCH_CHAINS
from ..state import load_state, state_path
from ..strategies import available_strategies, get_strategy, strategy_class

log = logging.getLogger(__name__)

WEB_ROOT = Path(__file__).resolve().parent.parent.parent / "web"
MAX_BODY_BYTES = 256 * 1024
# A grid search from a browser can run for minutes; keep the UI's reach modest.
MAX_BACKTEST_BARS = 20_000


class ApiError(Exception):
    """A request the client got wrong; reported as 4xx rather than a traceback."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


class CBotHandler(BaseHTTPRequestHandler):
    """Serves the dashboard's static files and its small JSON API."""

    server_version = "CBot"
    protocol_version = "HTTP/1.1"
    base_config: Config = None  # set by serve()

    # ------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
        route = urlparse(self.path)
        try:
            if route.path.startswith("/api/"):
                self._send_json(self._handle_api_get(route))
            else:
                self._serve_static(route.path)
        except ApiError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to a browser
            log.exception("GET %s failed", self.path)
            self._send_json({"error": f"internal error: {exc}"}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        try:
            if route.path == "/api/backtest":
                self._send_json(self._run_backtest(self._read_json()))
            elif route.path == "/api/research":
                self._send_json(self._run_research(self._read_json()))
            else:
                raise ApiError("no such endpoint", HTTPStatus.NOT_FOUND)
        except ApiError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
        except Exception as exc:  # noqa: BLE001
            log.exception("POST %s failed", self.path)
            self._send_json({"error": f"internal error: {exc}"}, status=500)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def _handle_api_get(self, route) -> dict:
        if route.path == "/api/strategies":
            return {"strategies": self._describe_strategies()}
        if route.path == "/api/config":
            return self._describe_config()
        if route.path == "/api/status":
            return self._describe_status()
        if route.path == "/api/chains":
            return {
                "chains": sorted(RESEARCH_CHAINS),
                "configured": bool(os.environ.get("ETHERSCAN_API_KEY")),
            }
        if route.path == "/api/symbols":
            params = parse_qs(route.query)
            return {"symbols": self._cached_symbols(params.get("timeframe", [None])[0])}
        raise ApiError("no such endpoint", HTTPStatus.NOT_FOUND)

    def _describe_strategies(self) -> list[dict]:
        out = []
        for name in available_strategies():
            if name.startswith("_"):  # test-only strategies
                continue
            cls = strategy_class(name)
            doc = (cls.__doc__ or "").strip().splitlines()
            out.append(
                {
                    "name": name,
                    "description": doc[0] if doc else "",
                    "params": [
                        {"name": key, "default": value}
                        for key, value in sorted(cls.default_params.items())
                    ],
                }
            )
        return out

    def _describe_config(self) -> dict:
        config = self.base_config
        return {
            "symbols": config.symbols,
            "timeframe": config.timeframe,
            "strategy": config.strategy.name,
            "exchange": config.exchange.name,
            "testnet": config.exchange.testnet,
            "mode": config.execution.mode,
            "starting_cash": config.execution.starting_cash,
            "fee_rate": config.execution.fee_rate,
            "slippage_pct": config.execution.slippage_pct,
            "risk": asdict(config.risk),
        }

    def _describe_status(self) -> dict:
        saved = load_state(state_path(self.base_config.state_dir))
        if not saved:
            return {"running": False, "positions": [], "message": "no saved state"}
        return {
            "running": True,
            "updated_at": saved.get("updated_at"),
            "cash": saved.get("cash", 0.0),
            "peak_equity": saved.get("peak_equity", 0.0),
            "realized_today": saved.get("realized_today", 0.0),
            "halted_reason": saved.get("halted_reason"),
            "positions": [
                {
                    "symbol": symbol,
                    "side": p.side.value,
                    "amount": p.amount,
                    "entry_price": p.entry_price,
                    "stop_price": p.stop_price,
                    "take_profit_price": p.take_profit_price,
                    "opened_at": p.opened_at.isoformat(),
                }
                for symbol, p in saved.get("positions", {}).items()
            ],
        }

    def _cached_symbols(self, timeframe: str | None) -> list[str]:
        """List symbols with cached candles, so the UI can offer real data."""
        data_dir = Path(self.base_config.data_dir)
        if not data_dir.exists():
            return []
        out = set()
        for path in data_dir.glob("*.csv"):
            symbol, _, found_tf = path.stem.rpartition("_")
            if not symbol:
                continue
            if timeframe and found_tf != timeframe:
                continue
            out.add(symbol.replace("-", "/"))
        return sorted(out)

    def _run_backtest(self, body: dict) -> dict:
        symbol = str(body.get("symbol") or self.base_config.symbols[0])
        timeframe = str(body.get("timeframe") or self.base_config.timeframe)
        strategy_name = str(body.get("strategy") or self.base_config.strategy.name)
        params = body.get("params") or {}
        if not isinstance(params, dict):
            raise ApiError("params must be an object")

        overrides = {
            "symbols": [symbol],
            "timeframe": timeframe,
            "execution": {
                "starting_cash": float(body.get("starting_cash") or self.base_config.execution.starting_cash),
                "fee_rate": float(body.get("fee_rate", self.base_config.execution.fee_rate)),
                "slippage_pct": float(body.get("slippage_pct", self.base_config.execution.slippage_pct)),
                "min_order_notional": self.base_config.execution.min_order_notional,
            },
            "risk": {**asdict(self.base_config.risk), **(body.get("risk") or {})},
            "data_dir": self.base_config.data_dir,
            "state_dir": self.base_config.state_dir,
        }
        try:
            config = from_dict(overrides)
        except ConfigError as exc:
            raise ApiError(str(exc)) from exc

        try:
            strategy = get_strategy(strategy_name, **params)
        except KeyError as exc:
            # str(KeyError) wraps the message in repr quotes; show the message itself.
            raise ApiError(exc.args[0]) from exc
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

        candles = self._load_candles(body, config, symbol, timeframe)

        try:
            result = Backtester(config, strategy).run(symbol, candles)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": result.strategy,
            "synthetic": bool(body.get("synthetic")),
            "metrics": result.metrics.as_dict(),
            "halted_reason": result.halted_reason,
            "rejections": result.rejections,
            "equity_curve": [
                {"t": p.timestamp.isoformat(), "equity": round(p.equity, 2)}
                for p in result.equity_curve
            ],
            "trades": [
                {
                    "opened_at": t.opened_at.isoformat(),
                    "closed_at": t.closed_at.isoformat(),
                    "side": t.side.value,
                    "amount": t.amount,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "net_pnl": t.net_pnl,
                    "return_pct": t.return_pct * 100,
                    "reason": t.reason,
                }
                for t in result.trades
            ],
        }

    def _run_research(self, body: dict) -> dict:
        """Review a token contract. Read-only public chain data, nothing else."""
        address = str(body.get("address") or "").strip()
        chain = str(body.get("chain") or "ethereum").strip()

        if not is_address(address):
            raise ApiError(
                "That does not look like a contract address. Paste the full address: "
                "0x followed by 40 hex characters."
            )

        try:
            researcher = ContractResearcher(chain)
        except SourceError as exc:
            raise ApiError(str(exc)) from exc

        try:
            report = researcher.review(address, deployer_limit=25)
        except AuthError as exc:
            # Fixable setup problem, not a bad request from the browser.
            raise ApiError(str(exc), HTTPStatus.SERVICE_UNAVAILABLE) from exc
        except SourceError as exc:
            raise ApiError(f"could not complete the review: {exc}", HTTPStatus.BAD_GATEWAY) from exc
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

        return report.as_dict()

    def _load_candles(self, body: dict, config: Config, symbol: str, timeframe: str):
        if body.get("synthetic"):
            bars = int(body.get("bars") or 3000)
            if not 100 <= bars <= MAX_BACKTEST_BARS:
                raise ApiError(f"bars must be between 100 and {MAX_BACKTEST_BARS}")
            return generate_synthetic(
                bars=bars, timeframe=timeframe, seed=int(body.get("seed") or 7)
            )
        try:
            # Never downloads: the dashboard reads the cache, `cbot fetch` fills it.
            return load_history(symbol, timeframe, data_dir=config.data_dir)
        except FileNotFoundError as exc:
            raise ApiError(
                f"no cached data for {symbol} {timeframe}. Run "
                f"`python -m tradingbot.cli fetch -s {symbol} -t {timeframe}` first, "
                f"or tick 'synthetic data'."
            ) from exc

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------
    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ApiError("request body too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        if length <= 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ApiError(f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ApiError("request body must be a JSON object")
        return payload

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB_ROOT / relative).resolve()

        # Refuse anything that escapes the web root, however it was encoded.
        if not target.is_relative_to(WEB_ROOT.resolve()) or not target.is_file():
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s - %s", self.address_string(), fmt % args)


def make_server(config: Config, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    handler = type("BoundCBotHandler", (CBotHandler,), {"base_config": config})
    return ThreadingHTTPServer((host, port), handler)


def serve(config: Config, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the dashboard until interrupted."""
    httpd = make_server(config, host, port)
    if host not in ("127.0.0.1", "localhost", "::1"):
        log.warning(
            "binding to %s exposes the dashboard beyond this machine; it has no "
            "authentication, so only do this on a trusted network",
            host,
        )

    print(f"\n  CBot dashboard: http://{host}:{port}\n  Ctrl-C to stop.\n")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\n  stopping…")
    finally:
        httpd.shutdown()
        httpd.server_close()
