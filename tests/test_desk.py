"""The operator's side of a handoff: claim, approve, reject, hand back, and what a retry or a stale screen may not do.

CLI-FIX0004 has one pending transfer (TXN-FIX0006, 15/01/2024). The review threshold is set to 0 days so that
movement counts as "too old" and the customer's yes becomes a ticket for a person instead of an opened trace.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.policy.desk import Conflict, DeskError, NotFound, default_desk
from agent.policy.escalation import default_queue
from agent.session.auth import SessionStore
from agent.tools import account_tools
from api import main
from eval.fake_llm import FakeLLMClient, text_response, tool_call_response


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var, name in (("HUMAN_QUEUE_PATH", "queue"), ("HUMAN_DESK_PATH", "desk"), ("TRACE_REQUESTS_PATH", "traces")):
        monkeypatch.setenv(var, str(tmp_path / f"{name}.jsonl"))
    monkeypatch.setattr(account_tools, "TRACE_REVIEW_AFTER_DAYS", 0)


def traces_opened() -> list[dict]:
    path = os.environ["TRACE_REQUESTS_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def file_ticket_in_session():
    """The customer asks to trace the pending transfer and says yes; the movement needs a person, so a ticket is filed."""
    fake = FakeLLMClient([tool_call_response("request_trace", {}), *[text_response("ok")] * 10])  # later turns just chat
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    tok = orch.session_store.issue("CLI-FIX0004", {"segment": "Student", "country": "México", "customer_status": "Active"}).token
    assert orch.handle_message(tok, "hice una transferencia que todavía no llega").policy_rule == "action:trace_proposed"
    r = orch.handle_message(tok, "sí")
    assert (r.disposition, r.policy_rule) == ("ESCALATE", "action:trace_review")
    return r.ticket_id, orch, tok


def file_ticket() -> str:
    return file_ticket_in_session()[0]


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


def test_the_operator_endpoints_need_the_operator_key_and_map_conflicts_to_409(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-key-0123456789-abcdefgh")
    monkeypatch.setenv("OPERATOR_KEYS", "ana=ana-key-0123456789-abcdefgh")
    client = TestClient(main.app)
    admin, ana = {"X-Admin-Key": "admin-key-0123456789-abcdefgh"}, {"X-Operator-Key": "ana-key-0123456789-abcdefgh"}
    ticket_id = file_ticket()
    body = {}
    assert client.post(f"/admin/tickets/{ticket_id}/claim", json=body).status_code == 401
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=ana).status_code == 409  # not claimed
    assert client.post(f"/admin/tickets/{ticket_id}/claim", json=body, headers=ana).json()["status"] == "claimed"
    assert client.get(f"/admin/tickets/{ticket_id}", headers=admin).json()["desk"]["operator"] == "ana"
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=ana).json()["status"] == "approved"
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=ana).status_code == 200  # idempotent
    assert client.post("/admin/tickets/none/claim", json=body, headers=ana).status_code == 404
    listed = client.get("/admin/human_queue", headers=admin).json()
    assert listed[-1]["desk"]["status"] == "approved"


def test_the_customer_hears_once_what_a_person_did_with_their_case():
    ticket_id, orch, tok = file_ticket_in_session()
    default_desk.act(ticket_id, "claim", "ana")
    said = orch.handle_message(tok, "gracias").response_text
    assert said.startswith("Novedad de tu caso: un agente ya lo tomó")
    assert "Novedad" not in orch.handle_message(tok, "gracias").response_text  # said once

    default_desk.act(ticket_id, "approve", "ana")
    said = orch.handle_message(tok, "gracias").response_text
    assert "aprobó el rastreo" in said and traces_opened()[0]["trace_id"] in said
    assert "Novedad" not in orch.handle_message(tok, "gracias").response_text  # a finished case is not repeated


def test_the_news_survives_a_restart_because_what_was_told_is_saved(tmp_path, monkeypatch):
    from agent.core.orchestrator import ConversationStore
    db = str(tmp_path / "state.sqlite")
    fake = FakeLLMClient([tool_call_response("request_trace", {}), *[text_response("ok")] * 10])

    def process():
        return Orchestrator(SessionStore(ttl_seconds=900, db_path=db), llm=lambda: fake, conversations=ConversationStore(db_path=db))

    before = process()
    tok = before.session_store.issue("CLI-FIX0004", {"segment": "Student", "country": "México", "customer_status": "Active"}).token
    before.handle_message(tok, "hice una transferencia que todavía no llega")
    ticket_id = before.handle_message(tok, "sí").ticket_id
    default_desk.act(ticket_id, "claim", "ana")
    assert "ya lo tomó" in before.handle_message(tok, "hola").response_text

    after = process()  # restarted: it must not repeat the news, and must still deliver what comes next
    assert "Novedad" not in after.handle_message(tok, "hola").response_text
    default_desk.act(ticket_id, "reject", "ana", reason="interno")
    said = after.handle_message(tok, "hola").response_text
    assert "no pudo abrir el rastreo" in said and "interno" not in said


@pytest.mark.parametrize("end_session", ["expire", "revoke"])
@pytest.mark.parametrize("action, expected", [("approve", "aprobó el rastreo"), ("reject", "no pudo abrir el rastreo")])
def test_case_news_follows_the_customer_after_login_and_conversation_cleanup(tmp_path, end_session, action, expected):
    import sqlite3
    from agent.core.orchestrator import ConversationStore

    db = str(tmp_path / "state.sqlite")
    fake = FakeLLMClient([tool_call_response("request_trace", {}), *[text_response("ok")] * 10])

    def process():
        return Orchestrator(SessionStore(db_path=db), llm=lambda: fake, conversations=ConversationStore(db_path=db))

    before = process()
    attrs = {"segment": "Student", "country": "México", "customer_status": "Active"}
    old = before.session_store.issue("CLI-FIX0004", attrs).token
    before.handle_message(old, "hice una transferencia que todavía no llega")
    ticket_id = before.handle_message(old, "sí").ticket_id
    default_desk.act(ticket_id, "claim", "ana")
    assert "ya lo tomó" in before.handle_message(old, "hola").response_text
    getattr(before.session_store, end_session)(old)

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE conversations SET updated_at = 0")
    after = process()
    token = after.session_store.issue("CLI-FIX0004", attrs).token
    assert "Novedad" not in after.handle_message(token, "hola").response_text
    default_desk.act(ticket_id, action, "ana")
    other = after.session_store.issue("CLI-FIX0001", attrs).token
    assert "Novedad" not in after.handle_message(other, "hola").response_text
    assert expected in after.handle_message(token, "hola").response_text

    restarted = process()
    newest = restarted.session_store.issue("CLI-FIX0004", attrs).token
    assert "Novedad" not in restarted.handle_message(newest, "hola").response_text


def test_the_case_endpoint_shows_a_customer_only_their_own_ticket(monkeypatch):
    ticket_id, orch, tok = file_ticket_in_session()
    monkeypatch.setattr(main.demo, "orchestrator_for", lambda token: orch)
    client = TestClient(main.app)
    default_desk.act(ticket_id, "claim", "ana")
    ok = client.get(f"/case/{ticket_id}", headers={"X-Session-Token": tok})
    assert ok.status_code == 200 and ok.json()["status"] == "claimed" and "ya lo tomó" in ok.json()["message"]
    other = orch.session_store.issue("CLI-FIX0001", {"segment": "Student", "country": "México", "customer_status": "Active"}).token
    assert client.get(f"/case/{ticket_id}", headers={"X-Session-Token": other}).status_code == 404
    assert client.get(f"/case/{ticket_id}", headers={"X-Session-Token": "not-a-session"}).status_code == 401
    assert client.get(f"/case/{ticket_id}").status_code == 401


def test_the_case_status_speaks_the_language_the_customer_is_writing_in_now_not_the_one_the_ticket_was_filed_in():
    """Nothing tells the API a UI language: the web's selector only sets a cookie for the pages. The reply language is read from the
    customer's own words on each turn and kept for the session, and both the news in the chat and GET /case/{id} use it. The ticket
    keeps the language it was filed in, and it is not what the customer is reading now."""
    ticket_id, orch, tok = file_ticket_in_session()
    assert default_queue.get(ticket_id)["language"] == "es"
    default_desk.act(ticket_id, "claim", "ana")
    assert "ya lo tomó" in orch.case_status(tok, ticket_id)["message"]

    news = orch.handle_message(tok, "quanto eu tenho de saldo na minha conta?")
    assert news.language == "pt" and news.response_text.startswith(render.case_update("claimed", "pt"))  # the chat's news agrees
    status = orch.case_status(tok, ticket_id)
    assert status["message"] == render.case_update("claimed", "pt") and "ya lo tomó" not in status["message"]

    orch.handle_message(tok, "ok")  # no language signal: the session keeps the last one, and so does the case
    assert orch.case_status(tok, ticket_id)["message"] == render.case_update("claimed", "pt")


def test_a_session_that_has_not_spoken_yet_reads_its_case_in_the_language_of_the_ticket():
    """A new session has no language of its own (the default is not something the customer chose). Asking for a ticket from an earlier
    session then falls back to the language the ticket was filed in; once the customer writes, the session's language wins."""
    fake = FakeLLMClient([tool_call_response("request_trace", {}), *[text_response("ok")] * 10])
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    attrs = {"segment": "Student", "country": "México", "customer_status": "Active"}
    first = orch.session_store.issue("CLI-FIX0004", attrs).token
    assert orch.handle_message(first, "fiz uma transferência que ainda não chegou").policy_rule == "action:trace_proposed"
    filed = orch.handle_message(first, "sim")
    assert (filed.disposition, filed.language) == ("ESCALATE", "pt") and default_queue.get(filed.ticket_id)["language"] == "pt"
    default_desk.act(filed.ticket_id, "claim", "ana")

    fresh = orch.session_store.issue("CLI-FIX0004", attrs).token  # a later login: no turns yet
    assert orch.case_status(fresh, filed.ticket_id)["message"] == render.case_update("claimed", "pt")
    orch.handle_message(fresh, "ok")  # says nothing about its language: still the ticket's
    assert orch.case_status(fresh, filed.ticket_id)["message"] == render.case_update("claimed", "pt")
    orch.handle_message(fresh, "cuál es mi saldo?")
    assert orch.case_status(fresh, filed.ticket_id)["message"] == render.case_update("claimed", "es")
