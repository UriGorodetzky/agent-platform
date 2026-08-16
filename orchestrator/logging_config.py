"""Structured (JSON) logging with a run_id correlation id.

Every log line is one JSON object on stdout — so a log aggregator can filter by
level, run_id, agent, etc. The run_id is carried in a ContextVar (async-aware,
like a thread-local) and injected into every record by a logging Filter, so we
never have to thread it through function calls.

These logs are the *developer's* view (diagnostics), complementing the *user's*
view (the domain events stored per run).
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# The current run's id, visible to any log call in the same async context.
run_id_var: ContextVar[str] = ContextVar("run_id", default="-")

# Attributes present on a vanilla LogRecord — everything else is a custom "extra".
_STANDARD_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class RunIdFilter(logging.Filter):
    """Attach the current run_id to every record (unless one was set explicitly)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = run_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single JSON line, including any extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": getattr(record, "run_id", "-"),
        }
        # Merge any fields passed via logger.x("msg", extra={...}).
        for key, value in record.__dict__.items():
            if key not in _STANDARD_KEYS and key != "run_id":
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Point the root logger at a single JSON-on-stdout handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RunIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
