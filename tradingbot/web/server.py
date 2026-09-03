"""HTTP server for the CBot dashboard.

Standard library only, so the site adds no dependencies. It binds to localhost by
default and is deliberately limited: it runs research and analysis, and it cannot
place an order. Live trading stays on the CLI where the confirmation locks are —
a browser tab is not somewhere a real order should be one click away.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..config import Config
from ..execution import FEE_TIERS
from ..research import AuthError, ContractResearcher, SourceError, is_address
from ..research.sources import CHAINS as RESEARCH_CHAINS
from . import api
from .api import ApiError
from .jobs import JobRunner

log = logging.getLogger(__name__)

WEB_ROOT = Path(__file__).resolve().parent.parent.parent / "web"
MAX_BODY_BYTES = 256 * 1024

#: Long-running endpoints run as background jobs and are polled.
JOB_KINDS = {"validate", "walkforward", "carry"}


class CBotHandler(BaseHTTPRequestHandler):
    """Serves the site's static files and its JSON API."""

    server_version = "CBot"
    protocol_version = "HTTP/1.1"
    base_config: Config = None       # set by make_server
    jobs: JobRunner = None           # set by make_server

    # ------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
        route = urlparse(self.path)
        try:
            if route.path.startswith("/api/"):
                self._send_json(self._get(route))
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
            self._send_json(self._post(route, self._read_json()))
        except ApiError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
        except Exception as exc:  # noqa: BLE001
            log.exception("POST %s failed", self.path)
            self._send_json({"error": f"internal error: {exc}"}, status=500)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def _get(self, route) -> dict:
        path = route.path
        params = parse_qs(route.query)
        config = self.base_config

        if path == "/api/strategies":
            return api.describe_strategies()
        if path == "/api/config":
            return api.describe_config(config)
        if path == "/api/status":
            return api.describe_status(config)
        if path == "/api/datasets":
            return api.describe_datasets(config)
        if path == "/api/execution":
            return api.describe_execution({"tier": (params.get("tier") or [None])[0]})
        if path == "/api/fee-tiers":
            return {
                "tiers": [
                    {"key": key, "name": tier.name, "maker": tier.maker, "taker": tier.taker}
                    for key, tier in sorted(FEE_TIERS.items())
                ]
            }
        if path == "/api/chains":
            return {
                "chains": sorted(RESEARCH_CHAINS),
                "configured": bool(os.environ.get("ETHERSCAN_API_KEY")),
            }
        if path == "/api/jobs":
            return {"jobs": [job.as_dict() for job in self.jobs.list_jobs()]}
        if path.startswith("/api/jobs/"):
            job = self.jobs.get(path.rsplit("/", 1)[-1])
            if job is None:
                raise ApiError("no such job", HTTPStatus.NOT_FOUND)
            return job.as_dict()

        raise ApiError("no such endpoint", HTTPStatus.NOT_FOUND)

    def _post(self, route, body: dict) -> dict:
        path = route.path
        config = self.base_config

        if path == "/api/backtest":
            return api.run_backtest(config, body)
        if path == "/api/regime":
            return api.run_regime(config, body)
        if path == "/api/research":
            return self._research(body)

        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            job_id = path.split("/")[3]
            if not self.jobs.cancel(job_id):
                raise ApiError("job is not running", HTTPStatus.CONFLICT)
            return {"cancelled": job_id}

        kind = path.rsplit("/", 1)[-1]
        if kind in JOB_KINDS:
            return self._start_job(kind, body)

        raise ApiError("no such endpoint", HTTPStatus.NOT_FOUND)

    def _start_job(self, kind: str, body: dict) -> dict:
        """Queue long work and hand back a job id to poll."""
        config = self.base_config

        if kind == "validate":
            runner = lambda ctx: api.run_validate(config, body, ctx)  # noqa: E731
        elif kind == "walkforward":
            runner = lambda ctx: api.run_walkforward(config, body, ctx)  # noqa: E731
        else:
            runner = lambda ctx: api.run_carry(body, ctx)  # noqa: E731

        job = self.jobs.submit(kind, runner)
        return job.as_dict()

    def _research(self, body: dict) -> dict:
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
            return researcher.review(address, deployer_limit=25).as_dict()
        except AuthError as exc:
            # A fixable setup problem, not a bad request from the browser.
            raise ApiError(str(exc), HTTPStatus.SERVICE_UNAVAILABLE) from exc
        except SourceError as exc:
            raise ApiError(f"could not complete the review: {exc}", HTTPStatus.BAD_GATEWAY) from exc
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

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
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s - %s", self.address_string(), fmt % args)


def make_server(config: Config, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    runner = JobRunner()
    handler = type(
        "BoundCBotHandler", (CBotHandler,), {"base_config": config, "jobs": runner}
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.job_runner = runner
    return httpd


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
        httpd.job_runner.shutdown()
        httpd.shutdown()
        httpd.server_close()
