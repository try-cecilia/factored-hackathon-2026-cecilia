"""Work that is given up on is still counted until it ends, and a limit on it holds: a stuck dependency cannot pile up threads.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from agent import observability
from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.llm.client import call_limit, deadline_transport
from agent.policy import escalation
from agent.session.auth import SessionStore
from agent.tools import account_tools
from eval.fake_llm import FakeLLMClient
from agent.resilience import bounded_ops_stats


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", "HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH"):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))
    from agent.policy import intent_guard

    intent_guard.read("hola")


def tickets() -> list[dict]:
    path = os.environ["HUMAN_QUEUE_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def orchestrator():
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: FakeLLMClient([]))
    return orch, orch.session_store.issue("CLI-FIX0001", {"segment": "Premium", "country": "México", "customer_status": "Active"}).token


def alive(name):
    return [t for t in threading.enumerate() if t.name == name]


def wait_until(check, seconds=3.0):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


# --- 2. a limit on the work left running --------------------------------------------------------------------------------

def test_with_a_stuck_dependency_many_turns_leave_at_most_the_limit_of_workers_and_the_rest_skip_the_evidence(monkeypatch):
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.05")
    monkeypatch.setenv("BOUNDED_OPS_LIMIT", "4")
    release = threading.Event()
    monkeypatch.setattr(account_tools, "recent_activity_for_review", lambda *a, **kw: release.wait(10) and {"items": []})
    orch, tok = orchestrator()
    try:
        results = [orch.handle_message(tok, "no reconozco un cargo en mi tarjeta") for _ in range(12)]
        assert len(alive("bounded")) <= 4 and bounded_ops_stats()["reads"]["inflight"] <= 4
        assert bounded_ops_stats()["reads"]["rejected"] >= 8  # the turns past the limit did not start another worker
        assert all(r.disposition == "ESCALATE" for r in results)
    finally:
        release.set()
    assert wait_until(lambda: bounded_ops_stats()["reads"]["inflight"] == 0 and not alive("bounded"))  # counted until the real work ended


def test_a_turn_past_the_limit_still_files_its_ticket_without_evidence(monkeypatch):
    monkeypatch.setenv("BOUNDED_OPS_LIMIT", "1")
    release = threading.Event()
    monkeypatch.setattr(account_tools, "recent_activity_for_review", lambda *a, **kw: release.wait(10) and {"items": []})
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.3")
    orch, tok = orchestrator()
    try:
        orch.handle_message(tok, "no reconozco un cargo en mi tarjeta")  # takes the only slot, and gives up on it
        second = orch.handle_message(tok, "no reconozco un cargo en mi tarjeta")
        assert second.ticket_id is None or second.ticket_id in [t["ticket_id"] for t in tickets()]
        assert any("Evidence was not gathered" in " ".join(t["open_questions"]) for t in tickets())
    finally:
        release.set()


def test_the_counts_reach_the_operators_endpoint_and_the_metrics(monkeypatch):
    from fastapi.testclient import TestClient

    from api import main

    body = TestClient(main.app).get("/admin/capacity", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert {"inflight", "rejected", "limit"} <= set(body["bounded_ops"]["reads"]) and "writes" in body["bounded_ops"]
    from agent import metrics

    text = metrics.default.render().decode()
    assert "cecilai_bounded_ops_inflight" in text and "cecilai_bounded_ops_rejected" in text and "cecilai_record_failures_total" in text


