"""The demo's console (api/demo_desk.py): a visitor signed in as a public sandbox customer acts, as the bank, on the cases that
same session filed, and on nothing else.

The switches (DEMO_MODE and DEMO_CONSOLE, each exactly "1") are walked for every route and role in tests/test_access_matrix.py.
Here: the session and the public account, the isolation between two visitors of the same public account (in the API, in the
customer's context and in the chat's news), the real desk's moves with their versions and conflicts, the predefined results
with the optional message, the trace an approval opens, the fixed actor and the limits.

CLI-FIX0004 has one pending transfer (TXN-FIX0006). The review threshold is set to 0 days so that the customer's yes to tracing
it becomes a ticket for a person (trace_review) instead of an opened trace.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.policy.desk import default_desk
from agent.policy.escalation import default_queue
from agent.session.auth import default_store
from agent.tools import account_tools
from agent.tools.traces import default_traces
from api import demo_desk, main
from api.limits import RateLimiter
from eval.fake_llm import FakeLLMClient, text_response, tool_call_response

PUBLIC = "CLI-FIX0004"
OTHER = "CLI-FIX0001"
ATTRS = {"segment": "Student", "country": "México", "customer_status": "Active"}


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    for var, name in (("HUMAN_QUEUE_PATH", "queue"), ("HUMAN_DESK_PATH", "desk"), ("TRACE_REQUESTS_PATH", "traces"),
                      ("AUDIT_LOG_PATH", "audit"), ("TRACE_LOG_PATH", "trace_log")):
        monkeypatch.setenv(var, str(tmp_path / f"{name}.jsonl"))
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_CONSOLE", "1")
    monkeypatch.setenv("DEMO_PUBLIC_CUSTOMERS", PUBLIC)
    monkeypatch.setattr(account_tools, "TRACE_REVIEW_AFTER_DAYS", 0)
    monkeypatch.setattr(demo_desk, "session_limiter", RateLimiter(1000, 60))
    monkeypatch.setattr(demo_desk, "customer_limiter", RateLimiter(1000, 60))
    monkeypatch.setattr(main, "chat_limiter", RateLimiter(1000, 60))


@pytest.fixture
def client():
    return TestClient(main.app)


def visitor(customer: str = PUBLIC) -> str:
    """A new session of the customer: on a public account, a new visitor."""
    return default_store.issue(customer, ATTRS).token


def h(token: str) -> dict:
    return {"X-Session-Token": token}


def say(client, token: str, text: str) -> dict:
    r = client.post("/chat", json={"session_token": token, "message": text})
    assert r.status_code == 200
    return r.json()


def theft_ticket(client, token: str, text: str = "me robaron la tarjeta") -> str:
    """A theft report: the lexicon hands it to a person before any model call, and the ticket carries no action."""
    reply = say(client, token, text)
    assert reply["disposition"] == "ESCALATE" and reply["ticket_id"]
    return reply["ticket_id"]


def trace_review_ticket(token: str) -> str:
    """The customer asks to trace the pending transfer and says yes; the movement needs a person, so a ticket is filed with it."""
    fake = FakeLLMClient([tool_call_response("request_trace", {}), *[text_response("ok")] * 10])
    orch = Orchestrator(default_store, llm=lambda: fake)
    assert orch.handle_message(token, "hice una transferencia que todavía no llega").policy_rule == "action:trace_proposed"
    r = orch.handle_message(token, "sí")
    assert (r.disposition, r.policy_rule) == ("ESCALATE", "action:trace_review")
    return r.ticket_id


def act(client, token: str, ticket_id: str, action: str, **body):
    return client.post(f"/demo/desk/tickets/{ticket_id}/{action}", headers=h(token), json=body)


def traces_file() -> list[dict]:
    path = os.environ["TRACE_REQUESTS_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


ROUTES = [("GET", "/demo/desk/tickets"), ("GET", "/demo/desk/tickets/{id}"), ("GET", "/demo/desk/tickets/{id}/customer_context"),
          ("POST", "/demo/desk/tickets/{id}/claim")]


def call(client, method: str, template: str, ticket_id: str, headers: dict):
    return client.request(method, template.replace("{id}", ticket_id), headers=headers, json={} if method == "POST" else None)


# --- who gets in --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("method,template", ROUTES)
def test_a_missing_unknown_expired_or_revoked_session_is_a_401(client, method, template):
    owner = visitor()
    ticket_id = theft_ticket(client, owner)
    expired, revoked = visitor(), visitor()
    default_store.expire(expired)
    default_store.revoke(revoked)
    for headers in ({}, h("0" * 24), h(expired), h(revoked)):
        r = call(client, method, template, ticket_id, headers)
        assert (r.status_code, r.json()) == (401, {"detail": "no live session"}), headers
    assert default_desk.state(ticket_id)["version"] == 0  # nothing was claimed


@pytest.mark.parametrize("method,template", ROUTES)
def test_an_account_that_is_not_public_is_a_403_and_the_list_is_read_on_every_call(client, monkeypatch, method, template):
    private = visitor(OTHER)
    ticket_id = theft_ticket(client, private)
    r = call(client, method, template, ticket_id, h(private))
    assert (r.status_code, r.json()) == (403, {"detail": "not a public sandbox account"})
    public = visitor()
    assert client.get("/demo/desk/tickets", headers=h(public)).status_code == 200
    monkeypatch.setenv("DEMO_PUBLIC_CUSTOMERS", OTHER)  # the account stops being public: the next call already knows
    assert client.get("/demo/desk/tickets", headers=h(public)).status_code == 403
    assert call(client, method, template, ticket_id, h(private)).status_code != 403


def test_the_session_and_the_account_are_rate_limited_with_a_retry_after(client, monkeypatch):
    monkeypatch.setattr(demo_desk, "session_limiter", RateLimiter(2, 60))
    a = visitor()
    assert [client.get("/demo/desk/tickets", headers=h(a)).status_code for _ in range(2)] == [200, 200]
    r = client.get("/demo/desk/tickets", headers=h(a))
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/demo/desk/tickets", headers=h(visitor())).status_code == 200  # another visitor has their own window

    monkeypatch.setattr(demo_desk, "session_limiter", RateLimiter(1000, 60))
    monkeypatch.setattr(demo_desk, "customer_limiter", RateLimiter(3, 60))
    assert [client.get("/demo/desk/tickets", headers=h(visitor())).status_code for _ in range(4)] == [200, 200, 200, 429]


# --- one visitor never reaches another's case ---------------------------------------------------------------------

def test_another_visitor_of_the_same_public_account_sees_nothing_of_a_case_and_cannot_tell_it_exists(client):
    a, b = visitor(), visitor()
    ticket_id = theft_ticket(client, a)

    assert client.get("/demo/desk/tickets", headers=h(b)).json() == []
    rows = client.get("/demo/desk/tickets", headers=h(a)).json()
    assert [r["ticket_id"] for r in rows] == [ticket_id] and rows[0]["desk"]["status"] == "open"

    stranger = str(uuid.uuid4())
    for method, template in ROUTES:
        theirs, nobodys = call(client, method, template, ticket_id, h(b)), call(client, method, template, stranger, h(b))
        if template == "/demo/desk/tickets":
            continue
        assert (theirs.status_code, theirs.json()) == (nobodys.status_code, nobodys.json()) == (404, {"detail": "ticket not found"})
    for action in ("approve", "reject", "release", "resolve"):
        assert act(client, b, ticket_id, action, result_code="will_contact").status_code == 404
    assert default_desk.state(ticket_id)["version"] == 0


def test_the_customer_context_lists_only_this_sessions_cases_and_traces(client):
    a, b = visitor(), visitor()
    mine, theirs = theft_ticket(client, a), theft_ticket(client, b)
    other_mine = theft_ticket(client, a, "me clonaron la tarjeta")
    pending = account_tools.request_trace(PUBLIC, transaction_id="TXN-FIX0006")["items"][0]
    default_traces.open(PUBLIC, "TXN-FIX0006", pending["product_id"], default_queue.get(theirs)["session_ref"])

    ctx = client.get(f"/demo/desk/tickets/{mine}/customer_context", headers=h(a)).json()
    assert [c["ticket_id"] for c in ctx["cases"]] == [other_mine]
    assert ctx["traces"] == [] and ctx["products"]  # the account's own data is still there
    admin = main.customer_context.for_ticket(default_queue.get(mine), default_queue, default_desk, default_traces)
    assert {c["ticket_id"] for c in admin["cases"]} == {other_mine, theirs} and len(admin["traces"]) == 1  # the team sees all

    audit = [json.loads(line) for line in open(os.environ["AUDIT_LOG_PATH"], encoding="utf-8")]
    reads = [e for e in audit if e.get("event") == "customer_context_read"]
    assert [(e["ticket_id"], e.get("actor")) for e in reads] == [(mine, "demo"), (mine, None)]  # the visitor's read, then the team's


# --- the real desk's moves, as "demo" ------------------------------------------------------------------------------

def test_claim_and_resolve_with_a_result_and_a_message_versions_and_conflicts(client):
    a = visitor()
    ticket_id = theft_ticket(client, a)
    detail = client.get(f"/demo/desk/tickets/{ticket_id}", headers=h(a)).json()
    assert detail["resolve_results"] == ["charge_confirmed", "will_contact", "call_the_bank"]
    assert detail["desk"]["version"] == 0

    assert act(client, a, ticket_id, "claim", expected_version=1).status_code == 409  # a stale screen
    claimed = act(client, a, ticket_id, "claim", expected_version=0)
    assert claimed.status_code == 200 and claimed.json()["status"] == "claimed" and claimed.json()["operator"] == "demo"

    assert act(client, a, ticket_id, "resolve", expected_version=1).status_code == 400  # no result
    assert act(client, a, ticket_id, "resolve", expected_version=1, message="listo").status_code == 400  # a message is not a result
    wrong = act(client, a, ticket_id, "resolve", expected_version=1, result_code="trace_not_possible")  # another family's
    assert (wrong.status_code, wrong.json()) == (422, {"detail": "that result is not one of this case's"})
    assert act(client, a, ticket_id, "resolve", expected_version=1, result_code="no_such_result").status_code == 422
    assert act(client, a, ticket_id, "resolve", expected_version=0, result_code="charge_confirmed").status_code == 409

    done = act(client, a, ticket_id, "resolve", expected_version=1, result_code="charge_confirmed",
               message="  Gracias por avisarnos   enseguida.  ")
    assert done.status_code == 200
    state = done.json()
    assert (state["status"], state["result"], state["message"]) == ("resolved", "charge_confirmed", "Gracias por avisarnos enseguida.")
    assert [e["operator"] for e in state["history"]] == ["demo", "demo"]  # the desk's audit: the actor is "demo"
    events = [json.loads(line) for line in open(os.environ["HUMAN_DESK_PATH"], encoding="utf-8")]
    assert {e["operator"] for e in events} == {"demo"}

    again = act(client, a, ticket_id, "resolve", result_code="charge_confirmed", message="Gracias por avisarnos enseguida.")
    assert again.status_code == 200 and again.json() == state  # a retry or a double click: the same outcome
    assert act(client, a, ticket_id, "resolve", result_code="call_the_bank").status_code == 409  # the customer already has the first
    assert act(client, a, ticket_id, "release").status_code == 409


def test_the_body_cannot_choose_the_actor_or_carry_fields_of_another_action(client):
    a = visitor()
    ticket_id = theft_ticket(client, a)
    for body in ({"operator": "ana"}, {"actor": "ana"}, {"expected_version": "0"}, {"expected_version": -1},
                 {"message": "x" * 501}, {"reason": "x" * 301}):
        assert act(client, a, ticket_id, "claim", **body).status_code == 422, body
    assert act(client, a, ticket_id, "claim", result_code="will_contact").status_code == 422
    assert act(client, a, ticket_id, "claim", message="hola").status_code == 422
    assert act(client, a, ticket_id, "claim", message="   ").status_code == 200  # blank is no message
    assert default_desk.state(ticket_id)["operator"] == "demo"


def test_a_case_a_real_operator_took_is_a_conflict_that_does_not_name_them(client):
    a = visitor()
    ticket_id = theft_ticket(client, a)
    default_desk.act(ticket_id, "claim", "ana")
    r = act(client, a, ticket_id, "claim")
    assert (r.status_code, r.json()) == (409, {"detail": "another person took this case"})
    assert "ana" not in r.text
    r = act(client, a, ticket_id, "resolve", result_code="will_contact")
    assert r.status_code == 409 and "ana" not in r.text


def test_approving_a_trace_opens_it_once_with_the_tickets_session(client):
    a = visitor()
    ticket_id = trace_review_ticket(a)
    detail = client.get(f"/demo/desk/tickets/{ticket_id}", headers=h(a)).json()
    assert detail["pending_action"]["transaction_id"] == "TXN-FIX0006" and detail["resolve_results"] == []
    assert traces_file() == []

    assert act(client, a, ticket_id, "claim", expected_version=0).status_code == 200
    assert act(client, a, ticket_id, "resolve", result_code="trace_not_possible").status_code == 422  # it is decided, not resolved
    first = act(client, a, ticket_id, "approve", expected_version=1)
    assert first.status_code == 200 and first.json()["status"] == "approved" and first.json()["trace_id"]
    again = act(client, a, ticket_id, "approve")
    assert again.status_code == 200 and again.json() == first.json()
    opened = traces_file()
    assert len(opened) == 1 and opened[0]["transaction_id"] == "TXN-FIX0006"
    assert opened[0]["session_ref"] == default_queue.get(ticket_id)["session_ref"] == default_store.validate(a).ref
    ctx = client.get(f"/demo/desk/tickets/{ticket_id}/customer_context", headers=h(a)).json()
    assert [t["trace_id"] for t in ctx["traces"]] == [first.json()["trace_id"]]
    assert act(client, a, ticket_id, "reject").status_code == 409


# --- what the customer reads ---------------------------------------------------------------------------------------

def test_the_visitor_reads_the_result_and_their_message_in_the_fixed_quote_and_no_other_visitor_does(client):
    a, b = visitor(), visitor()
    ticket_id = theft_ticket(client, a)
    act(client, a, ticket_id, "claim")
    act(client, a, ticket_id, "resolve", result_code="call_the_bank", message="Ya está en camino «la nueva».")

    assert "Novedad" not in say(client, b, "¿cuál es mi saldo?")["response_text"]  # B writes first: nothing of A's case
    assert client.get(f"/case/{ticket_id}", headers=h(b)).status_code == 404
    said = say(client, a, "¿cuál es mi saldo?")["response_text"]
    assert said.startswith("Novedad de tu caso: un agente lo resolvió. " + render.RESOLVE_RESULT["call_the_bank"]["es"]
                           + ' Mensaje del agente: «Ya está en camino "la nueva".»')
    assert "Novedad" not in say(client, a, "¿cuál es mi saldo?")["response_text"]  # said once
    case = client.get(f"/case/{ticket_id}", headers=h(a)).json()
    assert case["status"] == "resolved" and render.RESOLVE_RESULT["call_the_bank"]["es"] in case["message"]


def test_a_result_alone_has_no_quote_and_a_portuguese_session_reads_it_in_portuguese(client):
    a = visitor()
    ticket_id = theft_ticket(client, a, "roubaram meu cartão")
    act(client, a, ticket_id, "claim")
    assert act(client, a, ticket_id, "resolve", result_code="will_contact", message="").json()["message"] is None
    said = say(client, a, "quanto eu tenho de saldo na minha conta?")["response_text"]
    assert said.startswith("Novidade do seu caso: um atendente resolveu. " + render.RESOLVE_RESULT["will_contact"]["pt"])
    assert "Mensagem do atendente" not in said and "«" not in said.split("\n\n")[0]
