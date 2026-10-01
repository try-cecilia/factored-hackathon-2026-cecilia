"""The behavioral evidence (docs/BEHAVIORAL_EVIDENCE.md) is optional: when it cannot be computed the reviewer still gets the
customer's movements, only without the deviation, and nothing records the message of the error, only its type."""
from __future__ import annotations

import json
import os

import pytest

from agent.core.orchestrator import Orchestrator
from agent.policy import escalation
from agent.session.auth import SessionStore
from agent.tools import account_tools
from eval.fake_llm import FakeLLMClient

MARKER = "MARCADOR-SINTETICO-7f3a91 /srv/internal/bank.duckdb PRD-ZZ99ZZ99ZZ99"
CUSTOMER = "CLI-FIX0001"
STREAMS = ("HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH")


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", *STREAMS):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))


def boom(*_a, **_k):
    raise RuntimeError(MARKER)


def written() -> dict[str, str]:
    return {var: open(os.environ[var], encoding="utf-8").read() if os.path.exists(os.environ[var]) else "" for var in STREAMS}


def tickets() -> list[dict]:
    return [json.loads(line) for line in written()["HUMAN_QUEUE_PATH"].splitlines()]


def chat(message: str = "no reconozco un cargo en mi tarjeta"):
    from agent.policy import intent_guard

    intent_guard.read("hola")
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: FakeLLMClient([]))
    token = orch.session_store.issue(CUSTOMER, {"segment": "Premium", "country": "México", "customer_status": "Active"}).token
    return orch.handle_message(token, message)


def test_without_the_deviation_the_movements_are_kept(monkeypatch):
    baseline = account_tools.recent_activity_for_review(CUSTOMER, limit=10)["items"]
    assert baseline  # the fixture customer has movements to show
    monkeypatch.setattr(account_tools, "evidence_for", boom)
    result = account_tools.recent_activity_for_review(CUSTOMER, limit=10)
    assert [t["transaction_id"] for t in result["items"]] == [t["transaction_id"] for t in baseline]
    assert all(t["behavior"] is None for t in result["items"])
    assert result["behavior_error"] == "RuntimeError"  # the type of the failure, never its message
    assert MARKER not in json.dumps(result, default=str)


def test_a_failed_history_read_is_the_same_case(monkeypatch):
    real = account_tools._rows

    def rows(sql, params):
        if "transaction_country" in sql and "is_fraud" not in sql:  # the history read, not the movements
            raise RuntimeError(MARKER)
        return real(sql, params)

    monkeypatch.setattr(account_tools, "_rows", rows)
    result = account_tools.recent_activity_for_review(CUSTOMER, limit=10)
    assert result["items"] and all(t["behavior"] is None for t in result["items"])
    assert result["behavior_error"] == "RuntimeError"


def test_a_working_behavior_reports_no_error():
    assert "behavior_error" not in account_tools.recent_activity_for_review(CUSTOMER, limit=10)


def test_the_ticket_keeps_the_movements_and_the_marker_reaches_no_stream(monkeypatch):
    monkeypatch.setattr(account_tools, "evidence_for", boom)
    reply = chat()
    (ticket,) = tickets()
    assert reply.ticket_id == ticket["ticket_id"]
    movements = [e for e in ticket["evidence"] if e["type"] == "transaction"]
    assert movements and all(e["detail"]["behavior"] is None for e in movements)
    assert not any("evidence_failed" in json.dumps(c) for c in ticket["open_question_codes"])  # the movements were gathered
    for stream, text in written().items():
        assert text and "MARCADOR-SINTETICO" not in text and "bank.duckdb" not in text, stream
    audit = [json.loads(line) for line in written()["AUDIT_LOG_PATH"].splitlines()]
    review = next(a for a in audit if a.get("tool_name") == "recent_activity_for_review")
    assert review["success"] is True and review["result_summary"]["behavior_error"] == "RuntimeError"


def test_when_the_movements_themselves_fail_only_the_type_is_kept(monkeypatch):
    monkeypatch.setattr(account_tools, "_rows", boom)
    chat()
    (ticket,) = tickets()
    assert ticket["evidence"] == [] or all(e["type"] != "transaction" for e in ticket["evidence"])
    assert ticket["open_question_codes"][-1] == {"code": "evidence_failed", "params": {"error_type": "RuntimeError"}}
    assert ticket["open_questions"][-1] == "Could not gather recent activity automatically: RuntimeError"
    # the audit record of a failed tool call (audit.py) is the business of the branch that removes raw messages there
    assert "MARCADOR-SINTETICO" not in written()["HUMAN_QUEUE_PATH"]
