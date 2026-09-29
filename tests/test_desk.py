"""The operator's side of a handoff: claim, approve, reject, hand back, and what a retry or a stale screen may not do.

CLI-FIX0004 has one pending transfer (TXN-FIX0006, 15/01/2024). The review threshold is set to 0 days so that
movement counts as "too old" and the customer's yes becomes a ticket for a person instead of an opened trace.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from agent.core.orchestrator import Orchestrator
from agent.policy.desk import Conflict, DeskError, NotFound, default_desk
from agent.policy.escalation import default_queue
from agent.session.auth import SessionStore
from agent.tools import account_tools
from api import main
from eval.fake_llm import FakeLLMClient, tool_call_response


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var, name in (("HUMAN_QUEUE_PATH", "queue"), ("HUMAN_DESK_PATH", "desk"), ("TRACE_REQUESTS_PATH", "traces")):
        monkeypatch.setenv(var, str(tmp_path / f"{name}.jsonl"))
    monkeypatch.setattr(account_tools, "TRACE_REVIEW_AFTER_DAYS", 0)


def traces_opened() -> list[dict]:
    path = os.environ["TRACE_REQUESTS_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def file_ticket() -> str:
    """The customer asks to trace the pending transfer and says yes; the movement needs a person, so a ticket is filed."""
    fake = FakeLLMClient([tool_call_response("request_trace", {})])
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    tok = orch.session_store.issue("CLI-FIX0004", {"segment": "Student", "country": "México", "customer_status": "Active"}).token
    assert orch.handle_message(tok, "hice una transferencia que todavía no llega").policy_rule == "action:trace_proposed"
    r = orch.handle_message(tok, "sí")
    assert (r.disposition, r.policy_rule) == ("ESCALATE", "action:trace_review")
    return r.ticket_id


def test_a_movement_that_needs_a_person_is_not_traced_until_one_approves():
    ticket_id = file_ticket()
    ticket = default_queue.get(ticket_id)
    assert ticket["queue"] == "payments_ops" and ticket["pending_action"]["transaction_id"] == "TXN-FIX0006"
    assert traces_opened() == [] and default_desk.state(ticket_id)["status"] == "open"

    default_desk.act(ticket_id, "claim", "ana")
    state = default_desk.act(ticket_id, "approve", "ana")
    assert state["status"] == "approved"
    assert [t["transaction_id"] for t in traces_opened()] == ["TXN-FIX0006"]


def test_approving_twice_or_retrying_never_opens_a_second_trace():
    ticket_id = file_ticket()
    default_desk.act(ticket_id, "claim", "ana")
    first = default_desk.act(ticket_id, "approve", "ana")
    assert default_desk.act(ticket_id, "approve", "ana") == first  # a double click or a retry: the same outcome
    assert len(traces_opened()) == 1
    with pytest.raises(Conflict):
        default_desk.act(ticket_id, "reject", "ana")  # a finished ticket cannot be decided the other way


def test_an_approval_after_the_movement_settled_opens_nothing(monkeypatch):
    ticket_id = file_ticket()
    default_desk.act(ticket_id, "claim", "ana")
    real = account_tools.request_trace
    monkeypatch.setattr(account_tools, "request_trace", lambda customer_id, **kw: real(customer_id, **kw) | {"items": []})
    assert default_desk.act(ticket_id, "approve", "ana")["status"] == "stale"
    assert traces_opened() == []


def test_a_decision_needs_the_claim_and_is_refused_from_a_stale_screen_or_another_operator():
    ticket_id = file_ticket()
    with pytest.raises(Conflict):
        default_desk.act(ticket_id, "approve", "ana")  # not claimed yet
    seen = default_desk.state(ticket_id)["version"]
    default_desk.act(ticket_id, "claim", "ana")
    with pytest.raises(Conflict):
        default_desk.act(ticket_id, "claim", "beto")  # already ana's
    with pytest.raises(Conflict):
        default_desk.act(ticket_id, "approve", "beto")
    with pytest.raises(Conflict):
        default_desk.act(ticket_id, "approve", "ana", expected_version=seen)  # she saw it before her own claim
    assert traces_opened() == []


def test_reject_and_hand_back_open_nothing_and_are_final():
    rejected = file_ticket()
    default_desk.act(rejected, "claim", "ana")
    state = default_desk.act(rejected, "reject", "ana", reason="fecha incoherente con la cuenta")
    assert state["status"] == "rejected" and state["history"][-1]["detail"]["reason"].startswith("fecha")
    handed = file_ticket()
    default_desk.act(handed, "claim", "ana")
    assert default_desk.act(handed, "release", "ana")["status"] == "handed_back"
    assert traces_opened() == []
    with pytest.raises(Conflict):
        default_desk.act(handed, "claim", "ana")


def test_unknown_ticket_and_bad_input_are_refused():
    with pytest.raises(NotFound):
        default_desk.act("no-such-ticket", "claim", "ana")
    with pytest.raises(DeskError):
        default_desk.act("x", "delete", "ana")
    with pytest.raises(DeskError):
        default_desk.act("x", "claim", "  ")


def test_a_ticket_that_carries_no_action_cannot_be_approved():
    from agent.policy import router
    from agent.policy.escalation import escalate
    t = escalate(router.trace_step({"items": []}), "CLI-FIX0004", "ref", "no llegó", "es", [], [], [], {}, None)
    default_desk.act(t.ticket_id, "claim", "ana")
    with pytest.raises(Conflict):
        default_desk.act(t.ticket_id, "approve", "ana")


def test_the_operator_endpoints_need_the_admin_key_and_map_conflicts_to_409(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "k")
    client, hdr = TestClient(main.app), {"X-Admin-Key": "k"}
    ticket_id = file_ticket()
    body = {"operator": "ana"}
    assert client.post(f"/admin/tickets/{ticket_id}/claim", json=body).status_code == 401
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=hdr).status_code == 409  # not claimed
    assert client.post(f"/admin/tickets/{ticket_id}/claim", json=body, headers=hdr).json()["status"] == "claimed"
    assert client.get(f"/admin/tickets/{ticket_id}", headers=hdr).json()["desk"]["operator"] == "ana"
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=hdr).json()["status"] == "approved"
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=hdr).status_code == 200  # idempotent
    assert client.post("/admin/tickets/none/claim", json=body, headers=hdr).status_code == 404
    listed = client.get("/admin/human_queue", headers=hdr).json()
    assert listed[-1]["desk"]["status"] == "approved"
