"""A MOCK of the bank's payments-operations service for tracing a movement that is still pending.

The one action this workflow takes (D3). A trace request asks operations to follow a transfer, payment or deposit
that has not arrived. The challenge forbids live banking actions, so this is a sandbox: requests go to a JSONL file
next to the human queue (TRACE_REQUESTS_PATH). Opening is idempotent per customer and movement (the trace id is
derived from both), and the orchestrator reads a request back before telling the customer it exists.
TRACE_SLA_BUSINESS_DAYS is a synthetic policy, labeled as such.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

TRACE_SLA_BUSINESS_DAYS = 2  # synthetic policy


class TraceService:
    def __init__(self):
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        p = Path(os.environ.get("TRACE_REQUESTS_PATH", "data/warehouse/trace_requests.jsonl"))
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _all(self) -> list[dict]:
        # ponytail: a linear scan of a local JSONL file; the bank's case system answers these by key
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    @staticmethod
    def trace_id(customer_id: str, transaction_id: str) -> str:
        # 64 bits: with every pending movement of a bank traced, two alike are not expected in its lifetime.
        return "TR-" + hashlib.sha256(f"{customer_id}|{transaction_id}".encode()).hexdigest()[:16].upper()

    def get(self, trace_id: str) -> dict | None:
        return next((t for t in self._all() if t["trace_id"] == trace_id), None)

    def find(self, customer_id: str, transaction_id: str) -> dict | None:
        """This customer's request for this movement. Checked field by field: an id is never trusted to be unique."""
        return next((t for t in self._all() if t["trace_id"] == self.trace_id(customer_id, transaction_id)
                     and t["customer_id"] == customer_id and t["transaction_id"] == transaction_id), None)

    def open(self, customer_id: str, transaction_id: str, product_id: str, session_ref: str) -> dict:
        """The existing request for this movement, or a new one."""
        with self._lock:
            existing = self.find(customer_id, transaction_id)
            if existing:
                return existing
            request = {"trace_id": self.trace_id(customer_id, transaction_id), "customer_id": customer_id,
                       "transaction_id": transaction_id, "product_id": product_id, "session_ref": session_ref,
                       "created_at": time.time(), "status": "open", "sla_business_days": TRACE_SLA_BUSINESS_DAYS,
                       "queue": "payments_ops"}
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(request, ensure_ascii=False) + "\n")
            return request

    def clear(self, customer_id: str) -> int:
        """Sandbox only: forget a customer's requests, so a demo scenario starts from a clean state."""
        with self._lock:
            everything = self._all()
            keep = [t for t in everything if t["customer_id"] != customer_id]
            self.path.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in keep), encoding="utf-8")
            return len(everything) - len(keep)


default_traces = TraceService()
