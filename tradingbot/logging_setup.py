"""Logging configuration: readable on the console, complete in the log file."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

CONSOLE_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
FILE_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"


def setup_logging(level: str = "INFO", log_dir: str | Path | None = "logs") -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(console)

    if log_dir:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        # Always DEBUG on disk: when a live trade goes wrong the detail matters.
        file_handler = RotatingFileHandler(
            path / "tradingbot.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(file_handler)

    # ccxt logs every HTTP call at INFO, which drowns out our own output.
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
