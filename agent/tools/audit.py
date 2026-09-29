"""Append-only execution records: every tool call and every conversation turn.

Two JSONL streams, both keyed by trace_id so a turn can be reconstructed
end to end (the "execution records" an auditor reads instead of any hidden
model reasoning):
- audit_log.jsonl: one line per tool call (args, outcome, duration).
- traces.jsonl:    one line per turn (LLM attempts + usage, tool calls,
                   policy decision, latency, cost).
Only a bounded window of recent records is kept in memory.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent import metrics
from agent.filelock import append_line

current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_trace_id", default=None)


@dataclass
class ToolCallRecord:
    call_id: str
    trace_id: str | None
    tool_name: str
    session_customer_id: str
    args: dict[str, Any]
    started_at: float
    finished_at: float | None = None
    success: bool | None = None
    result_summary: Any = None
    error: str | None = None
    error_type: str | None = None

    @property
    def duration_ms(self) -> float | None:
        return None if self.finished_at is None else round((self.finished_at - self.started_at) * 1000, 2)


class _JsonlSink:
    def __init__(self, env_var: str, default: str, keep: int):
        self._env_var, self._default = env_var, default
        self._recent: deque = deque(maxlen=keep)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        p = Path(os.environ.get(self._env_var, self._default))
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write(self, record: dict) -> None:
        line = json.dumps(record, default=str, ensure_ascii=False)
        with self._lock:
            self._recent.append(record)
            append_line(self.path, line)  # under the file lock, so a retention purge never swaps the file in mid-write

    def recent(self) -> list[dict]:
        return list(self._recent)


def _observe(count) -> None:
    """Metrics are a side view of the record just written: they never break the turn that produced it."""
    try:
        count()
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("could not update metrics")


class AuditLog:
    def __init__(self):
        self._sink = _JsonlSink("AUDIT_LOG_PATH", "data/warehouse/audit_log.jsonl", keep=1000)

    @property
    def path(self) -> Path:
        return self._sink.path

    def start(self, tool_name: str, session_customer_id: str, args: dict[str, Any]) -> ToolCallRecord:
        return ToolCallRecord(str(uuid.uuid4()), current_trace_id.get(), tool_name, session_customer_id, args, time.time())

    def finish(self, record: ToolCallRecord, success: bool, result_summary: Any = None, error: Exception | None = None) -> None:
        record.finished_at = time.time()
        record.success = success
        record.result_summary = result_summary
        if error is not None:
            record.error, record.error_type = str(error), type(error).__name__
        self._sink.write({**asdict(record), "duration_ms": record.duration_ms})
        seconds = None if record.duration_ms is None else record.duration_ms / 1000
        _observe(lambda: metrics.default.observe_tool_call(record.tool_name, seconds, record.trace_id))

    def event(self, kind: str, **fields: Any) -> None:
        """A record that is not a tool call (a failed operator login). `started_at` lets ops/retention.py prune it."""
        self._sink.write({"event": kind, "started_at": time.time(), "trace_id": current_trace_id.get(), **fields})

    def recent(self) -> list[dict]:
        return self._sink.recent()


class TraceLog:
    def __init__(self):
        self._sink = _JsonlSink("TRACE_LOG_PATH", "data/warehouse/traces.jsonl", keep=500)

    @property
    def path(self) -> Path:
        return self._sink.path

    def write(self, trace: dict) -> None:
        self._sink.write(trace)
        _observe(lambda: metrics.default.observe_turn(trace))  # /metrics counts what the trace says (agent/metrics.py)

    def recent(self) -> list[dict]:
        return self._sink.recent()


default_audit_log = AuditLog()
default_trace_log = TraceLog()
