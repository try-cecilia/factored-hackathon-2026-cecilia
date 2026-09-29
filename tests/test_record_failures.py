"""A record that cannot be written never takes the customer's confirmed result with it: the effects (a ticket filed, a
trace opened) already happened, so the reply must go out, and the failure is counted and logged on another channel."""
from __future__ import annotations

import json
import logging
import os

import pytest
from fastapi.testclient import TestClient

from agent import observability
from agent.core import orchestrator as orch_mod
from agent.core.orchestrator import Orchestrator
from agent.session import identity
from agent.session.auth import SessionStore
from agent.session.identity import derive_test_pin
from api import main
from eval.fake_llm import FakeLLMClient, tool_call_response


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", "HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH"):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))


def sink_down(monkeypatch):
    def boom(record):
        raise OSError("disk full")

    monkeypatch.setattr(orch_mod.default_trace_log, "write", boom)


def orchestrator(script, customer="CLI-FIX0001"):
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: FakeLLMClient(script))
    return orch, orch.session_store.issue(customer, {"segment": "Premium", "country": "México", "customer_status": "Active"}).token


def test_the_trace_sink_failing_after_a_ticket_was_filed_still_returns_the_handoff(monkeypatch, caplog):
    orch, tok = orchestrator([])
    sink_down(monkeypatch)
    before = observability.failure_counts().get("trace_write", 0)
    with caplog.at_level(logging.ERROR):
        r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert (r.disposition, r.category) == ("ESCALATE", "theft") and r.ticket_id
    assert [json.loads(line)["ticket_id"] for line in open(os.environ["HUMAN_QUEUE_PATH"])] == [r.ticket_id]  # filed, and told
    assert observability.failure_counts()["trace_write"] == before + 1
    failed = [rec for rec in caplog.records if getattr(rec, "fields", {}).get("kind") == "trace_write"]
    assert failed and failed[0].fields["trace_id"] == r.trace_id and "disk full" not in caplog.text  # type only, no message


def test_the_trace_sink_failing_after_a_trace_was_opened_still_tells_the_customer(monkeypatch):
    orch, tok = orchestrator([tool_call_response("request_trace", {})], customer="CLI-FIX0004")
    orch.handle_message(tok, "hice una transferencia que todavía no llega")
    sink_down(monkeypatch)
    r = orch.handle_message(tok, "sí")
    assert r.policy_rule == "action:trace_opened" and "TR-" in r.response_text
    assert len(open(os.environ["TRACE_REQUESTS_PATH"]).read().splitlines()) == 1


def test_a_conversation_that_cannot_be_saved_is_counted_too(monkeypatch):
    orch, tok = orchestrator([])
    monkeypatch.setattr(orch.conversations, "save", lambda key: (_ for _ in ()).throw(OSError("db locked")))
    before = observability.failure_counts().get("conversation_save", 0)
    assert orch.handle_message(tok, "Me clonaron la tarjeta").ticket_id
    assert observability.failure_counts()["conversation_save"] == before + 1


def test_over_http_it_is_a_200_with_the_ticket_not_a_500_and_the_count_is_readable_by_operators(monkeypatch):
    identity.default_identity._failures.clear()
    client = TestClient(main.app, raise_server_exceptions=False)
    tok = client.post("/auth/session", json={"customer_id": "CLI-FIX0001", "pin": derive_test_pin("CLI-FIX0001")}).json()["token"]
    sink_down(monkeypatch)
    r = client.post("/chat", json={"session_token": tok, "message": "Me clonaron la tarjeta"})
    assert r.status_code == 200 and r.json()["ticket_id"] and r.json()["trace_id"] == r.headers["X-Request-ID"]
    state = client.get("/admin/capacity", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert state["failures"]["trace_write"] >= 1
