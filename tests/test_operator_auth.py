"""Autenticación del operador: eventos de auditoría, limitador de fallos y endpoints de acción del desk."""
from __future__ import annotations

import json

from agent.tools.audit import AuditLog
from api import main


def test_an_audit_event_carries_a_timestamp_so_retention_can_prune_it(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    AuditLog().event("operator_auth_failed", origin="1.2.3.4", reason="invalid")
    row = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["event"] == "operator_auth_failed" and row["origin"] == "1.2.3.4" and isinstance(row["started_at"], float)


def test_the_failure_limiter_counts_only_recorded_failures_and_per_origin():
    limiter = main.RateLimiter(2, 60)
    assert not limiter.over("a")          # looking never counts
    assert not limiter.over("a")
    limiter.record("a")
    assert not limiter.over("a")
    limiter.record("a")
    assert limiter.over("a") and not limiter.over("b")
