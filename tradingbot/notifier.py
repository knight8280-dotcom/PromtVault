"""Trade notifications.

Defaults to logging. A webhook URL in $TRADINGBOT_WEBHOOK_URL (Slack-compatible)
turns on outbound posts; a failed notification never interrupts trading.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

WEBHOOK_ENV = "TRADINGBOT_WEBHOOK_URL"


class Notifier:
    """Posts short status messages, if a webhook is configured."""

    def __init__(self, webhook_url: str | None = None, timeout: float = 5.0) -> None:
        self.webhook_url = webhook_url or os.environ.get(WEBHOOK_ENV)
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def send(self, message: str, level: int = logging.INFO) -> None:
        log.log(level, message)
        if not self.enabled:
            return
        try:
            request = urllib.request.Request(
                self.webhook_url,
                data=json.dumps({"text": message}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(request, timeout=self.timeout).close()
        except (urllib.error.URLError, OSError) as exc:
            # A broken webhook must never take the bot down.
            log.warning("notification failed: %s", exc)

    def trade_opened(self, symbol: str, side: str, amount: float, price: float, reason: str) -> None:
        self.send(f"OPEN  {side.upper()} {amount:.6f} {symbol} @ {price:,.2f} — {reason}")

    def trade_closed(self, symbol: str, pnl: float, price: float, reason: str) -> None:
        marker = "+" if pnl >= 0 else ""
        self.send(f"CLOSE {symbol} @ {price:,.2f} — {reason} — P&L {marker}{pnl:,.2f}")

    def halted(self, reason: str) -> None:
        self.send(f"HALTED: {reason}", level=logging.ERROR)

    def error(self, message: str) -> None:
        self.send(f"ERROR: {message}", level=logging.ERROR)
