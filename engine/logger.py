"""Structured logging for AgentSwarm."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class NdjsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach structured data if present.
        data = getattr(record, "data", None)
        if data:
            entry["data"] = data
        return json.dumps(entry, default=str)


class HumanFormatter(logging.Formatter):
    """Compact one-line format for terminal display."""

    COLORS = {
        "DEBUG": "\033[90m",     # grey
        "INFO": "\033[36m",      # cyan
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now().strftime("%H:%M:%S")
        name = record.name.replace("agentswarm.", "")
        msg = record.getMessage()
        data = getattr(record, "data", None)
        suffix = ""
        if data:
            suffix = f"  {json.dumps(data, default=str)}"
        return f"{color}{ts} [{record.levelname[0]}] {name}: {msg}{suffix}{self.RESET}"


def setup_logging(level: str = "info", log_file: str | None = None) -> None:
    """Configure the agentswarm root logger."""
    root = logging.getLogger("agentswarm")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    # Console: human-readable
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(HumanFormatter())
    root.addHandler(console)

    # Optional file: NDJSON
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(NdjsonFormatter())
        root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under agentswarm namespace."""
    return logging.getLogger(f"agentswarm.{name}")
