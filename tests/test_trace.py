"""D3, the one action this workflow takes: tracing a movement that is still pending.

The model only picks request_trace. The code finds the movement, proposes it, and opens the trace only after the
customer confirms with a plain yes, deterministically and without the model; it reads the trace back before
saying it exists. Fixture: CLI-FIX0004 has one pending transfer (TXN-FIX0006, 40.00 USD, 15/01/2024, savings
···0010); CLI-FIX0001 has nothing pending.
"""
from __future__ import annotations

import json
import os

import pytest

from agent.core.orchestrator import Orchestrator
from agent.policy import router
from agent.session.auth import SessionStore
from agent.tools import traces
from eval.fake_llm import FakeLLMClient, tool_call_response


@pytest.fixture(autouse=True)
def trace_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_REQUESTS_PATH", str(tmp_path / "trace_requests.jsonl"))
    return tmp_path / "trace_requests.jsonl"


def stored() -> list[dict]:
    path = os.environ["TRACE_REQUESTS_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def make(*responses, customer="CLI-FIX0004"):
    fake = FakeLLMClient(list(responses))
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    tok = orch.session_store.issue(customer, {"segment": "Student", "country": "México", "customer_status": "Active"}).token
    return orch, tok, fake


def test_a_pending_transfer_is_proposed_and_traced_only_after_the_customer_says_yes():
    orch, tok, fake = make(tool_call_response("request_trace", {}))
    r1 = orch.handle_message(tok, "hice una transferencia que todavía no llega")
    assert (r1.disposition, r1.category, r1.policy_rule) == ("CLARIFY", "confirm_action", "action:trace_proposed")
    assert "40.00 USD" in r1.response_text and "15/01/2024" in r1.response_text and "···0010" in r1.response_text
    assert stored() == []  # nothing is opened before the customer confirms
    assert "40" not in (r1.model_view or "")  # the model's history keeps no figures

    r2 = orch.handle_message(tok, "sí")
    assert (r2.disposition, r2.policy_rule, r2.llm_calls) == ("AUTO_RESOLVE", "action:trace_opened", 0)
    [trace] = stored()
    assert trace["transaction_id"] == "TXN-FIX0006" and trace["trace_id"] in r2.response_text
    assert "2 días hábiles" in r2.response_text and r2.verified_facts[0]["tool"] == "request_trace"
    assert fake.call_count == 1  # the confirmation never reached the model


def test_a_plain_no_opens_nothing():
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    orch.handle_message(tok, "hice una transferencia que todavía no llega")
    r = orch.handle_message(tok, "no, gracias")
    assert (r.disposition, r.category, r.policy_rule) == ("ABSTAIN", "action_cancelled", "action:trace_cancelled")
    assert stored() == []


def test_anything_but_a_plain_answer_drops_the_proposal_and_goes_through_the_usual_checks():
    orch, tok, _ = make(tool_call_response("request_trace", {}), tool_call_response("get_account_summary", {}))
    orch.handle_message(tok, "hice una transferencia que todavía no llega")
    assert orch.handle_message(tok, "no, me clonaron la tarjeta").disposition == "ESCALATE"  # the safety lexicon ran
    assert orch.handle_message(tok, "sí").policy_rule != "action:trace_opened"  # the proposal lapsed
    assert stored() == []


def test_asking_again_returns_the_same_trace_instead_of_a_new_one():
    orch, tok, _ = make(tool_call_response("request_trace", {}), tool_call_response("request_trace", {}))
    orch.handle_message(tok, "¿pueden rastrear mi transferencia? sigue pendiente")
    opened = orch.handle_message(tok, "dale")
    again = orch.handle_message(tok, "¿y mi transferencia pendiente?")
    assert (again.disposition, again.policy_rule) == ("AUTO_RESOLVE", "action:trace_already_open")
    assert len(stored()) == 1 and stored()[0]["trace_id"] in opened.response_text and stored()[0]["trace_id"] in again.response_text


def test_a_trace_that_does_not_read_back_is_never_announced(monkeypatch):
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    orch.handle_message(tok, "hice una transferencia que todavía no llega")
    monkeypatch.setattr(traces.TraceService, "get", lambda self, trace_id: None)  # the write was lost
    r = orch.handle_message(tok, "sí")
    assert (r.disposition, r.policy_rule) == ("ESCALATE", "action:trace_unverified") and r.ticket_id
    assert "abrí" not in r.response_text.lower()


def test_with_nothing_pending_a_person_checks_it():
    orch, tok, _ = make(tool_call_response("request_trace", {}), customer="CLI-FIX0001")
    r = orch.handle_message(tok, "me hicieron una transferencia y nunca llegó")
    assert (r.disposition, r.category) == ("ESCALATE", "trace_unmatched") and r.ticket_id
    ticket = json.loads(open(os.environ["HUMAN_QUEUE_PATH"], encoding="utf-8").read().splitlines()[-1])
    assert ticket["queue"] == "payments_ops" and ticket["ticket_id"] == r.ticket_id


def test_another_customers_product_cannot_be_traced():
    orch, tok, _ = make(tool_call_response("request_trace", {"product_id": "PRD-FIX0001"}))
    r = orch.handle_message(tok, "rastreen el depósito de esa cuenta")
    assert (r.disposition, r.category) == ("ESCALATE", "security") and stored() == []


def test_several_pending_movements_make_the_customer_pick_one():
    items = [{"transaction_id": t, "transaction_date": "2024-01-15 10:00:00", "transaction_type": "Transfer", "amount": 40,
              "currency": "USD", "product_id": "PRD-FIX0010", "last4": "0010", "product_type": "Cuenta Ahorro", "open_trace": None}
             for t in ("TXN-A", "TXN-B")]
    decision = router.trace_step({"items": items})
    assert (decision.disposition.value, decision.rule) == ("CLARIFY", "action:trace_choose")


def test_the_pre_llm_guard_hands_few_trace_requests_to_a_person():
    """12 team-written trace requests, never used for training (eval/test_cases/trace_requests_heldout.csv). The
    intent classifier predates the trace action; one of them reads as a possible dispute and goes to a person,
    which is safe but not self-served (LIMITATIONS.md). Retraining with trace examples cost a fraud report on the
    classifier's held-out test, so the classifier was kept."""
    import csv

    from agent.policy.signals import escalation_categories
    from agent.policy import intent_guard

    rows = list(csv.DictReader(open("eval/test_cases/trace_requests_heldout.csv", encoding="utf-8")))
    escalated = [r["utterance"] for r in rows if escalation_categories(r["utterance"]) or intent_guard.read(r["utterance"]).escalate]
    assert len(rows) == 12 and escalated == ["necesito que rastreen un pago que no se acreditó"]


@pytest.mark.parametrize("text,answer", [
    ("sí", "yes"), ("Si", "yes"), ("SÍ, por favor", "yes"), ("dale", "yes"), ("confirmo", "yes"), ("sim", "yes"),
    ("pode ser", "yes"), ("ok", "yes"), ("no", "no"), ("No, gracias", "no"), ("cancelar", "no"), ("não", "no"),
    ("nao obrigado", "no"), ("sí, pero antes dime mi saldo", None), ("no sé", None), ("¿cuánto tengo?", None),
])
def test_only_a_plain_answer_counts_as_confirming_or_refusing(text, answer):
    assert router.confirmation(text) == answer
