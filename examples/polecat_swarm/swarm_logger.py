"""Structured JSON logging for Polecat Swarm."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from .types import TraceContext

logging.basicConfig(level=logging.INFO, format="%(message)s")

LogSink = Callable[[dict], None]
_LOG_SINKS: list[LogSink] = []


def register_log_sink(sink: LogSink) -> None:
    """Register a best-effort callback for each structured log record."""
    if sink not in _LOG_SINKS:
        _LOG_SINKS.append(sink)


def unregister_log_sink(sink: LogSink) -> None:
    """Remove previously registered sink."""
    if sink in _LOG_SINKS:
        _LOG_SINKS.remove(sink)


class SwarmLogger:
    """Emit structured JSON log records carrying trace metadata."""

    def __init__(self, trace: TraceContext):
        self._trace = trace
        self._logger = logging.getLogger("polecat_swarm")

    def _emit(self, level: str, event: str, **fields) -> None:
        record = {
            "ts": round(time.time(), 3),
            "level": level,
            "event": event,
            "trace_id": self._trace.trace_id,
            "span_id": self._trace.span_id,
            "sub_span_id": self._trace.sub_span_id,
            "role": self._trace.expert_role,
            "repo": self._trace.repo_name,
            "elapsed_s": round(self._trace.elapsed(), 3),
        }
        record.update(fields)
        getattr(self._logger, level.lower())(json.dumps(record))
        for sink in list(_LOG_SINKS):
            try:
                sink(record)
            except Exception:
                # Sinks are non-critical side channels (e.g., WS bridge).
                continue

    def info(self, event: str, **fields) -> None:
        self._emit("INFO", event, **fields)

    def warn(self, event: str, **fields) -> None:
        self._emit("WARNING", event, **fields)

    def error(self, event: str, **fields) -> None:
        self._emit("ERROR", event, **fields)

    def debug(self, event: str, **fields) -> None:
        self._emit("DEBUG", event, **fields)
