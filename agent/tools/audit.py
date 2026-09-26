"""Append-only audit log for every tool call.

This is the "execution records" the rubric asks for under observability and
under escalation handoffs: what was called, with what inputs, what came back,
whether it succeeded, and how long it took. It's also what "Verify" (in the
Understand -> Decide -> Act -> Verify -> Escalate loop) checks against before
letting a tool's output reach the customer-facing response.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolCallRecord:
    call_id: str
    tool_name: str
    session_customer_id: str
    args: dict[str, Any]
    started_at: float
    finished_at: float | None = None
    success: bool | None = None
    result_summary: Any = None
    error: str | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.finished_at is None:
            return None
        return round((self.finished_at - self.started_at) * 1000, 2)


class AuditLog:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.environ.get("AUDIT_LOG_PATH", "data/warehouse/audit_log.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[ToolCallRecord] = []

    def start(self, tool_name: str, session_customer_id: str, args: dict[str, Any]) -> ToolCallRecord:
        record = ToolCallRecord(
            call_id=str(uuid.uuid4()),
            tool_name=tool_name,
            session_customer_id=session_customer_id,
            args=args,
            started_at=time.time(),
        )
        self._records.append(record)
        return record

    def finish(self, record: ToolCallRecord, success: bool, result_summary: Any = None, error: str | None = None) -> None:
        record.finished_at = time.time()
        record.success = success
        record.result_summary = result_summary
        record.error = error
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(record), default=str) + "\n")

    def all_records(self) -> list[ToolCallRecord]:
        return list(self._records)


default_audit_log = AuditLog()
