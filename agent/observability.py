"""Correlation ids, per-stage timings and structured logs: one turn, one trace id, from the HTTP request to the ticket.

- The API gives every request a trace id (32 lowercase hex, the size of a W3C trace id) and returns it as
  `X-Request-ID` and in `traceparent`. The orchestrator adopts it as the turn's `trace_id`, so the same id is in the
  response body, the trace record, every tool audit record, the escalation ticket and each log line of the turn.
- A caller's own ids are kept beside it, not in place of it: an incoming `traceparent` becomes `upstream_trace_id`
  and an incoming `X-Request-ID` becomes `client_request_id` (both validated: a client cannot choose our trace id, so
  two turns never share one and a lookup by id finds one turn).
- Stages: the orchestrator times each step of a turn (`stage("llm")`) and the trace record gets one entry per step with
  its start offset, duration and outcome: the shape of an OpenTelemetry span, so an exporter can be added without
  changing what is recorded. Nothing here imports OpenTelemetry; without an exporter there is nothing to configure.
- Logs carry the trace id and identifiers only: never what the customer wrote, a reply, a figure or a customer id.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import re
import secrets
import time
import uuid
from typing import Any, Iterator

from agent.tools.audit import current_trace_id  # the one context variable audit records already read

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")

current_request: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("current_request", default=None)
current_stages: contextvars.ContextVar["StageRecorder | None"] = contextvars.ContextVar("current_stages", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return secrets.token_hex(8)


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    """(trace id, parent span id) of a valid W3C `traceparent`, else None. All-zero ids are invalid by the spec."""
    m = _TRACEPARENT.match((value or "").strip().lower())
    if not m or set(m.group(1)) == {"0"} or set(m.group(2)) == {"0"}:
        return None
    return m.group(1), m.group(2)


def format_traceparent(trace_id: str, span_id: str) -> str:
    return f"00-{trace_id}-{span_id}-01"


def clean_request_id(value: str | None) -> str | None:
    """A caller's request id when it is short and made of plain characters; anything else is dropped, not repaired."""
    return value.strip() if value and _REQUEST_ID.match(value.strip()) else None


def request_context(headers: Any) -> dict[str, Any]:
    """What to record about the caller's own ids, from request headers (any mapping with case-insensitive `get`)."""
    ctx: dict[str, Any] = {}
    parsed = parse_traceparent(headers.get("traceparent"))
    if parsed:
        ctx["upstream_trace_id"], ctx["upstream_span_id"] = parsed
    if rid := clean_request_id(headers.get("x-request-id")):
        ctx["client_request_id"] = rid
    return ctx


class StageRecorder:
    """The timed steps of one turn, on the monotonic clock, as span-shaped records."""

    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self.spans: list[dict[str, Any]] = []

    def add(self, name: str, started: float, outcome: str, **fields: Any) -> None:
        now = time.perf_counter()
        self.spans.append({"span_id": new_span_id(), "stage": name, "start_ms": round((started - self._t0) * 1000, 2),
                           "ms": round((now - started) * 1000, 2), "outcome": outcome, **fields})


@contextlib.contextmanager
def stage(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Time a step of the turn. `outcome` is "ok" unless the block raises (then the exception's type) or sets
    `info["outcome"]`. A no-op outside a turn. The block's exception is never swallowed."""
    rec = current_stages.get()
    info: dict[str, Any] = {}
    started = time.perf_counter()
    try:
        yield info
    except BaseException as exc:
        if rec is not None:
            rec.add(name, started, type(exc).__name__, **fields, **{k: v for k, v in info.items() if k != "outcome"})
        raise
    else:
        if rec is not None:
            rec.add(name, started, str(info.get("outcome", "ok")), **fields, **{k: v for k, v in info.items() if k != "outcome"})


@contextlib.contextmanager
def recording() -> Iterator[StageRecorder]:
    rec = StageRecorder()
    token = current_stages.set(rec)
    try:
        yield rec
    finally:
        current_stages.reset(token)


# --- logs ---------------------------------------------------------------------------------------------------------

class TraceIdFilter(logging.Filter):
    """Stamps each record with the trace id of the request or turn that is running, if any."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Extra fields come from `logger.info(msg, extra={"fields": {...}})`."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {"ts": round(record.created, 3), "level": record.levelname, "logger": record.name,
                               "trace_id": getattr(record, "trace_id", "-"), "msg": record.getMessage()}
        out.update(getattr(record, "fields", {}) or {})
        if record.exc_info:
            out["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None  # no traceback text: it can quote data
        return json.dumps(out, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Every log line of the app carries the trace id. LOG_FORMAT=json writes one JSON object per line (what a log
    shipper wants); the default is plain text with the id in brackets. Safe to call more than once."""
    root = logging.getLogger()
    if any(getattr(h, "_cecilai", False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler._cecilai = True  # type: ignore[attr-defined]
    handler.addFilter(TraceIdFilter())
    handler.setFormatter(JsonFormatter() if os.environ.get("LOG_FORMAT") == "json"
                         else logging.Formatter("%(asctime)s %(levelname)s [%(trace_id)s] %(name)s: %(message)s"))
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    for noisy in ("httpx", "httpcore"):  # one line per outbound call, with nothing the turn log does not already say
        logging.getLogger(noisy).setLevel(logging.WARNING)
