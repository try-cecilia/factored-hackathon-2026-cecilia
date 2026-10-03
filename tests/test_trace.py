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

from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.policy import router
from agent.session.auth import SessionStore, session_ref
from agent.tools import traces
from eval.fake_llm import FakeLLMClient, text_response, tool_call_response

ASK = {"es": "hice una transferencia que todavía no llega", "pt": "fiz uma transferência que ainda não chegou"}


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


def proposal(orch, tok) -> dict | None:
    """The trace proposal the conversation keeps in code for the next turn, if any."""
    return orch.conversations.get(session_ref(tok)).pending_action


@pytest.mark.parametrize("lang,yes,sla", [("es", "sí", "2 días hábiles"), ("pt", "sim", "2 dias úteis")])
def test_a_pending_transfer_is_proposed_and_traced_only_after_the_customer_says_yes(lang, yes, sla):
    orch, tok, fake = make(tool_call_response("request_trace", {}))
    r1 = orch.handle_message(tok, ASK[lang])
    assert (r1.disposition, r1.category, r1.policy_rule) == ("CLARIFY", "confirm_action", "action:trace_proposed")
    assert "40.00 USD" in r1.response_text and "15/01/2024" in r1.response_text and "···0010" in r1.response_text
    assert stored() == []  # nothing is opened before the customer confirms
    assert "40" not in (r1.model_view or "")  # the model's history keeps no figures

    r2 = orch.handle_message(tok, yes)
    assert (r2.disposition, r2.policy_rule, r2.llm_calls, r2.language) == ("AUTO_RESOLVE", "action:trace_opened", 0, lang)
    [trace] = stored()
    assert trace["transaction_id"] == "TXN-FIX0006" and trace["trace_id"] in r2.response_text
    assert sla in r2.response_text and r2.verified_facts[0]["tool"] == "request_trace"
    assert fake.call_count == 1  # the confirmation never reached the model


@pytest.mark.parametrize("lang,no", [("es", "no"), ("es", "No"), ("es", "no, gracias"), ("pt", "não"), ("pt", "Não")])
def test_a_plain_no_opens_nothing(lang, no):
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    orch.handle_message(tok, ASK[lang])
    r = orch.handle_message(tok, no)
    assert (r.disposition, r.category, r.policy_rule) == ("ABSTAIN", "action_cancelled", "action:trace_cancelled")
    assert r.language == lang  # a Spanish "no" used to read as Portuguese and switch the conversation
    assert stored() == [] and proposal(orch, tok) is None


@pytest.mark.parametrize("lang,no", [("es", "No"), ("pt", "não")])
def test_declining_a_trace_answers_in_the_conversation_s_language(lang, no):
    """The "Ahora no" button sends "No". In a Spanish conversation the answer was "Entendido, não abri nenhum
    pedido…": "no" counted as Portuguese. It carries no signal now, so the conversation keeps its language."""
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    assert orch.handle_message(tok, ASK[lang]).language == lang
    r = orch.handle_message(tok, no)
    assert (r.policy_rule, r.language, r.response_text) == ("action:trace_cancelled", lang, render.MSG["trace_cancelled"][lang])
    assert orch.conversations.get(session_ref(tok)).language == lang


def test_anything_but_a_plain_answer_drops_the_proposal_and_goes_through_the_usual_checks():
    orch, tok, _ = make(tool_call_response("request_trace", {}), tool_call_response("get_account_summary", {}))
    orch.handle_message(tok, "hice una transferencia que todavía no llega")
    assert orch.handle_message(tok, "no, me clonaron la tarjeta").disposition == "ESCALATE"  # the safety lexicon ran
    assert orch.handle_message(tok, "sí").policy_rule != "action:trace_opened"  # the proposal lapsed
    assert stored() == []


@pytest.mark.parametrize("lang,answer", [
    ("es", "SÍÍÍ"), ("es", "👍"), ("es", "sí pero no"), ("es", "no, sí, bueno, dale... no sé"),
    ("es", "Claro que no me lo vas a rastrear, ¿no?"), ("es", "Si fuera vos lo rastrearía"),
    ("pt", "SIIIM"), ("pt", "👍"), ("pt", "sim mas não"), ("pt", "não, sim, bom, tá bom... não sei"),
    ("pt", "Claro que você não vai rastrear, né?"), ("pt", "Se fosse você eu rastrearia"),
])
def test_an_answer_that_is_not_a_plain_yes_opens_nothing_and_a_later_yes_does_not_revive_the_proposal(lang, answer):
    """Answers the red team gave to a fresh, valid proposal, looking for a trace opened without a clear yes
    (docs/red_team_guia.md). None is a plain yes: nothing is opened, the proposal lapses and the message goes on as a
    new one, and a plain yes on a later turn finds nothing to confirm. The controls, a plain yes, sim and no on the
    same proposal, are the tests above."""
    orch, tok, fake = make(tool_call_response("request_trace", {}), text_response("¿En qué más te ayudo?"),
                           text_response("¿En qué más te ayudo?"))
    assert stored() == [] and proposal(orch, tok) is None
    assert orch.handle_message(tok, ASK[lang]).policy_rule == "action:trace_proposed"
    assert proposal(orch, tok)["transaction_id"] == "TXN-FIX0006"

    r = orch.handle_message(tok, answer)
    assert r.policy_rule not in ("action:trace_opened", "action:trace_cancelled")
    assert stored() == [] and proposal(orch, tok) is None

    later = orch.handle_message(tok, "sim" if lang == "pt" else "sí")
    assert later.policy_rule != "action:trace_opened"
    assert stored() == [] and proposal(orch, tok) is None


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
    monkeypatch.setattr(traces.TraceService, "find", lambda self, customer_id, transaction_id: None)  # the write was lost
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
    ("claro que sim", "yes"), ("sí sí", "yes"), ("sale", "yes"), ("va", "yes"), ("por supuesto", "yes"), ("correcto", "yes"),
    ("ok dale", "yes"), ("sim, pode", "yes"), ("yes please", "yes"), ("no no", "no"), ("mejor no", "no"), ("não quero", "no"),
])
def test_only_a_plain_answer_counts_as_confirming_or_refusing(text, answer):
    assert router.confirmation(text) == answer


def test_a_trace_id_collision_never_announces_another_customers_trace(monkeypatch):
    """With colliding ids, one customer's trace must never be found or announced for another (review finding I2)."""
    monkeypatch.setattr(traces.TraceService, "trace_id", staticmethod(lambda customer_id, transaction_id: "TR-SAME"))
    service = traces.TraceService()
    service.open("CLI-FIX0001", "TXN-OTHER", "PRD-FIX0001", "someone-else")
    assert service.find("CLI-FIX0004", "TXN-FIX0006") is None
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    r = orch.handle_message(tok, "hice una transferencia que todavía no llega")
    assert r.policy_rule == "action:trace_proposed"  # not "already open" with the other customer's number


def test_clearing_a_customers_traces_never_leaves_the_file_half_written(trace_store, monkeypatch):
    """The demo's reset rewrites the file other visitors are reading: the new content must appear whole or not at
    all (review minor #6). If the swap fails, every request is still there and no temporary file is left behind."""
    service = traces.TraceService()
    service.open("CLI-FIX0004", "TXN-FIX0006", "PRD-FIX0010", "a-jury-run")
    service.open("CLI-FIX0001", "TXN-OTHER", "PRD-FIX0001", "someone-else")
    before = trace_store.read_text(encoding="utf-8")

    def swap_fails(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", swap_fails)
    with pytest.raises(OSError):
        service.clear("CLI-FIX0004")
    assert trace_store.read_text(encoding="utf-8") == before
    # no temporary file; the store's lock file (agent/filelock.py) is a stable sidecar, not a leftover
    assert [p.name for p in trace_store.parent.iterdir() if not p.name.endswith(".lock")] == [trace_store.name]


def test_trace_ids_are_long_enough_that_a_bank_never_sees_two_alike():
    assert len(traces.TraceService.trace_id("CLI-FIX0004", "TXN-FIX0006")) == len("TR-") + 16


def test_a_pending_movement_can_be_picked_by_its_number_in_the_list(monkeypatch):
    """Several pending movements: the list is kept server side, and "la segunda" picks the second, in code
    (review finding I3). The customer then confirms it as usual."""
    from agent.core import orchestrator as orch_mod
    from agent.tools import account_tools

    real = account_tools.request_trace
    first = {"transaction_id": "TXN-FIX0006", "transaction_date": "2024-01-15 10:00:00", "transaction_type": "Transfer",
             "amount": 40, "currency": "USD", "product_id": "PRD-FIX0010", "product_type": "Cuenta Ahorro", "last4": "0010", "open_trace": None}
    second = {**first, "transaction_id": "TXN-FIX0099", "transaction_type": "Deposit", "amount": 15, "transaction_date": "2024-01-14 09:00:00"}
    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "request_trace",
                        lambda customer_id, **kw: real(customer_id, **kw) | {"items": [first, second]})
    orch, tok, fake = make(tool_call_response("request_trace", {}))
    listed = orch.handle_message(tok, "tengo movimientos que no se acreditan")
    assert listed.policy_rule == "action:trace_choose" and "1)" in listed.response_text and "2)" in listed.response_text
    proposed = orch.handle_message(tok, "la segunda")
    assert (proposed.policy_rule, proposed.llm_calls) == ("action:trace_proposed", 0) and "15.00 USD" in proposed.response_text
    opened = orch.handle_message(tok, "sí")
    assert opened.policy_rule == "action:trace_opened" and stored()[0]["transaction_id"] == "TXN-FIX0099"
    assert fake.call_count == 1


@pytest.mark.parametrize("text,n,index", [
    ("la segunda", 2, 1), ("2", 2, 1), ("el primero", 2, 0), ("la 1", 3, 0), ("a segunda", 2, 1), ("o primeiro", 2, 0),
    ("número 2", 2, 1), ("la tercera", 2, None), ("la de 40 dólares", 2, None), ("la segunda y la primera", 2, None),
])
def test_an_ordinal_picks_from_the_list_only_when_it_is_the_whole_answer(text, n, index):
    assert router.ordinal(text, n) == index


def test_a_movement_that_settled_after_the_proposal_is_not_traced(monkeypatch):
    """The yes answers a proposal one turn old: eligibility is checked again, and a person takes over."""
    from agent.core import orchestrator as orch_mod
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    assert orch.handle_message(tok, "hice una transferencia que todavía no llega").policy_rule == "action:trace_proposed"
    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "request_trace", lambda *a, **k: {"items": []})  # it is no longer Pending
    r = orch.handle_message(tok, "sí")
    assert (r.disposition, r.policy_rule) == ("ESCALATE", "action:trace_unmatched")
    assert stored() == []


def test_a_movement_pushed_past_the_candidate_cap_is_still_traced_on_confirmation(monkeypatch):
    """Found by amount/date, then five newer pendings crowd it out of a top-N list: the re-check asks for it by id."""
    from agent.tools import account_tools
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    assert orch.handle_message(tok, "hice una transferencia que todavía no llega").policy_rule == "action:trace_proposed"
    monkeypatch.setattr(account_tools, "MAX_TRACE_CANDIDATES", 0)  # a list query would now return nothing
    r = orch.handle_message(tok, "sí")
    assert r.policy_rule == "action:trace_opened" and len(stored()) == 1
