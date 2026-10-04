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
    monkeypatch.setenv("HUMAN_QUEUE_PATH", str(tmp_path / "human_queue.jsonl"))
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


TRACE_RULE = {"rule_id": "trace_deadline", "version": 2, "country": "MX", "operation": "Trace", "kind": "deadline",
              "currency": "USD", "value": 3, "unit": "business days", "valid_from": "2026-10-01",
              "source": {"issuer": "Payments regulator", "url": "https://example.test/trace", "checked_at": "2026-10-01",
                         "officially_reviewed": True}}


def deadline_rule(**changes):
    """A trace deadline rule as the catalog loads it: through its validation, never built around it."""
    from agent.policy.payment_rules import validate_catalog

    [rule] = validate_catalog({"schema_version": 1, "rules": [{**TRACE_RULE, **changes}]})
    return rule


def test_legacy_trace_sla_is_never_repeated_in_a_customer_update():
    update = render.case_update("approved", "es", trace={"trace_id": "TR-1", "sla_business_days": 2})
    assert update == "Novedad de tu caso: un agente aprobó el rastreo y abrió el pedido TR-1."


@pytest.mark.parametrize("lang,yes,words", [("es", "sí", "Plazo respaldado: 3 días hábiles. Regla v2, vigente desde 01/10/2026"),
                                            ("pt", "sim", "Prazo respaldado: 3 dias úteis. Regra v2, vigente desde 01/10/2026")])
def test_a_trace_snapshots_and_shows_only_a_country_rule_for_its_deadline(monkeypatch, lang, yes, words):
    from agent.policy import payment_rules

    monkeypatch.setattr(payment_rules, "resolve_rules", lambda *args, **kwargs: [deadline_rule()])
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    orch.handle_message(tok, ASK[lang])
    opened = orch.handle_message(tok, yes)
    [trace] = stored()
    assert trace["service_rules"][0]["rule_id"] == "trace_deadline" and trace["sla_business_days"] == 3
    assert words in opened.response_text and "business days" not in opened.response_text
    assert "Payments regulator" in opened.response_text and "https://example.test/trace" in opened.response_text
    # the receipt of #18 carries the same deadline, from the same snapshot
    assert opened.trace_receipt["sla_business_days"] == 3 and opened.trace_receipt["read_back"] is True


@pytest.mark.parametrize("lang,yes", [("es", "sí"), ("pt", "sim")])
def test_without_a_country_rule_the_trace_still_reads_back_with_a_receipt_and_no_deadline(lang, yes):
    # the production catalog is empty: a trace that reads back is announced, with its receipt, and no deadline is invented
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    orch.handle_message(tok, ASK[lang])
    opened = orch.handle_message(tok, yes)
    assert (opened.disposition, opened.policy_rule) == ("AUTO_RESOLVE", "action:trace_opened")
    [trace] = stored()
    assert trace["sla_business_days"] is None and "service_rules" not in trace
    assert opened.trace_receipt is not None and opened.trace_receipt["trace_id"] == trace["trace_id"]
    assert opened.trace_receipt["sla_business_days"] is None
    assert not any(word in opened.response_text for word in ("hábil", "útil", "útei", "Plazo", "Prazo"))


@pytest.mark.parametrize("lang,yes", [("es", "sí"), ("pt", "sim")])
def test_a_legacy_record_with_the_synthetic_sla_never_revives_it(lang, yes):
    # a record written before the country rules says 2 days and has no rule: the receipt and the reply say no deadline
    from agent.core.orchestrator import _trace_receipt_for

    movement = {"transaction_id": "TXN-FIX0006", "transaction_date": "2024-01-15", "amount": 40.0, "currency": "USD",
                "transaction_type": "Transfer", "transaction_status": "Pending"}
    legacy = {"trace_id": traces.default_traces.trace_id("CLI-FIX0004", "TXN-FIX0006"), "transaction_id": "TXN-FIX0006",
              "status": "open", "sla_business_days": 2}
    receipt = _trace_receipt_for(movement, legacy, "CLI-FIX0004")
    assert receipt is not None and receipt["sla_business_days"] is None
    assert render.trace_service_text(legacy.get("service_rules", []), lang) == ""


@pytest.mark.parametrize("lang,expected", [("es", "Plazo respaldado: 0 días hábiles."), ("pt", "Prazo respaldado: 0 dias úteis.")])
def test_a_backed_deadline_of_zero_is_said_and_an_incomplete_rule_is_not(lang, expected):
    from agent.policy.payment_rules import deadline_business_days, snapshot

    [zero] = snapshot([deadline_rule(value=0)])
    assert render.trace_service_text([zero], lang).startswith("\n" + expected)
    assert deadline_business_days([zero]) == 0
    for missing in ("value", "unit", "source_url", "valid_from"):
        incomplete = {k: v for k, v in zero.items() if k != missing}
        assert render.trace_service_text([incomplete], lang) == "", missing
    assert deadline_business_days([{**zero, "value": None}]) is None
    assert deadline_business_days(None) is None and deadline_business_days([zero, zero]) is None


@pytest.mark.parametrize("changes", [{"value": 5, "unit": "calendar days"}, {"value": 1.5}, {"kind": "commission", "unit": "USD"},
                                     {"value": 2, "unit": "weeks"}])
def test_a_trace_rule_that_is_not_a_whole_number_of_business_days_is_refused_by_the_catalog(changes):
    # the reply, the receipt and the bank view say the same deadline only if it is whole business days: anything else is refused
    with pytest.raises(ValueError):
        deadline_rule(**changes)


def test_a_whole_trace_deadline_written_as_a_decimal_loads_as_that_integer():
    assert deadline_rule(value=4.0).value == 4 and isinstance(deadline_rule(value=4.0).value, int)


@pytest.mark.parametrize("days", [0, 1, 4])
@pytest.mark.parametrize("lang,yes,one,many", [("es", "sí", "1 día hábil", "días hábiles"), ("pt", "sim", "1 dia útil", "dias úteis")])
def test_the_reply_and_the_receipt_say_the_same_deadline(monkeypatch, days, lang, yes, one, many):
    from agent.policy import payment_rules

    monkeypatch.setattr(payment_rules, "load_catalog", lambda: [deadline_rule(value=days)])
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    orch.handle_message(tok, ASK[lang])
    opened = orch.handle_message(tok, yes)
    said = one if days == 1 else f"{days} {many}"
    assert f"respaldado: {said}." in opened.response_text
    assert opened.trace_receipt["sla_business_days"] == days and stored()[0]["sla_business_days"] == days


@pytest.mark.parametrize("lang,words", [("es", "1 día hábil"), ("pt", "1 dia útil")])
def test_an_agent_approved_trace_carries_the_country_rule_and_the_customer_hears_it(monkeypatch, lang, words):
    from agent.policy import payment_rules
    from agent.policy.desk import TicketDesk

    seen = {}

    def resolve(country, operation, kind, currency, on_date, **_):
        seen.update(country=country, operation=operation, kind=kind, currency=currency)
        return [deadline_rule(value=1)]

    monkeypatch.setattr(payment_rules, "resolve_rules", resolve)
    ticket = {"customer_id": "CLI-FIX0004", "session_ref": "ref",
              "pending_action": {"transaction_id": "TXN-FIX0006", "product_id": "PRD-FIX0010"}}
    outcome, trace = TicketDesk._execute(ticket, ticket["pending_action"])
    assert outcome == "opened" and trace["sla_business_days"] == 1
    assert seen == {"country": "México", "operation": "Trace", "kind": "deadline", "currency": "USD"}  # verified, from SQL
    assert words in render.case_update("approved", lang, trace)


@pytest.mark.parametrize("lang,yes", [("es", "sí"), ("pt", "sim")])
def test_a_pending_transfer_is_proposed_and_traced_only_after_the_customer_says_yes(lang, yes):
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
    assert "hábiles" not in r2.response_text and "úteis" not in r2.response_text
    assert r2.verified_facts[0]["tool"] == "request_trace"
    assert fake.call_count == 1  # the confirmation never reached the model


def test_the_receipt_uses_the_as_of_date_from_the_confirmation_read(monkeypatch):
    from agent.core import orchestrator as orchestrator_module

    original = orchestrator_module.run_tool
    request_reads = 0

    def updated_warehouse_read(*args, **kwargs):
        nonlocal request_reads
        result = original(*args, **kwargs)
        if args[0] == "request_trace":
            request_reads += 1
            if request_reads == 2:  # the confirmation revalidation
                result = {**result, "as_of": "2024-01-17"}
        return result

    monkeypatch.setattr(orchestrator_module, "run_tool", updated_warehouse_read)
    orch, tok, _ = make(tool_call_response("request_trace", {}))
    orch.handle_message(tok, ASK["es"])
    opened = orch.handle_message(tok, "sí")

    assert opened.trace_receipt["data_as_of"] == "2024-01-17"


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


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_with_nothing_pending_a_person_checks_it_and_the_customer_is_told_why(lang):
    orch, tok, _ = make(tool_call_response("request_trace", {}), customer="CLI-FIX0001")
    r = orch.handle_message(tok, ASK[lang])
    assert (r.disposition, r.category, r.policy_rule, r.language) == ("ESCALATE", "trace_unmatched", "action:trace_unmatched", lang) and r.ticket_id
    assert r.response_text == render.MSG["trace_unmatched"][lang]
    ticket = json.loads(open(os.environ["HUMAN_QUEUE_PATH"], encoding="utf-8").read().splitlines()[-1])
    assert ticket["queue"] == "payments_ops" and ticket["ticket_id"] == r.ticket_id


@pytest.mark.parametrize("lang", ["es", "pt"])
@pytest.mark.parametrize("narrowed_by", [{"amount": "999"}, {"on_date": "2024-02-20"}])
def test_a_narrowed_search_that_matches_nothing_does_not_say_nothing_is_pending(lang, narrowed_by):
    """CLI-FIX0004 has a pending transfer (40.00 USD, 15/01/2024): a search by another amount or date finds nothing, and the
    customer hears that nothing matched, never that nothing is pending, and nothing of the movement the search left out."""
    orch, tok, _ = make(tool_call_response("request_trace", narrowed_by))
    r = orch.handle_message(tok, ASK[lang])
    assert (r.disposition, r.policy_rule) == ("ESCALATE", "action:trace_unmatched") and r.ticket_id
    assert r.response_text == render.MSG["trace_unmatched_filtered"][lang]
    assert not any(f in r.response_text for f in ("40", "15/01/2024", "0010")) and stored() == []


def test_with_nothing_pending_and_a_ticket_that_does_not_read_back_the_customer_is_not_told_of_a_handoff(monkeypatch):
    from agent.policy import escalation

    monkeypatch.setattr(escalation.default_queue, "get", lambda ticket_id: None)  # the write was lost
    orch, tok, _ = make(tool_call_response("request_trace", {}), customer="CLI-FIX0001")
    r = orch.handle_message(tok, "me hicieron una transferencia y nunca llegó")
    assert (r.disposition, r.policy_rule, r.ticket_id) == ("ESCALATE", "action:trace_unmatched|handoff_unverified", None)
    assert r.response_text == render.MSG["escalate_unverified"]["es"].format(code=r.trace_id[:8])


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


def test_sequential_payments_keep_the_first_trace_and_open_only_the_selected_second(monkeypatch):
    from agent.core import orchestrator as orch_mod
    from agent.tools import account_tools

    real = account_tools.request_trace
    first = real("CLI-FIX0004")["items"][0]
    second = {**first, "transaction_id": "TXN-FIX0099", "amount": 15, "transaction_type": "Payment", "open_trace": None}

    def candidates(customer_id, **filters):
        if filters.get("transaction_id"):
            items = [first if filters["transaction_id"] == first["transaction_id"] else second]
        else:
            items = [first, second]
        if filters.get("amount") is not None:
            amount = float(filters["amount"])
            items = [item for item in items if float(item["amount"]) == amount]
        return {"items": [{**item, "open_trace": traces.default_traces.find(customer_id, item["transaction_id"])}
                           for item in items]}

    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "request_trace", candidates)
    orch, tok, _ = make(tool_call_response("request_trace", {}), tool_call_response("request_trace", {}),
                        tool_call_response("request_trace", {"amount": 40}))

    choices = orch.handle_message(tok, "rastrea mis pagos pendientes")
    assert choices.policy_rule == "action:trace_choose"
    assert orch.handle_message(tok, "1").policy_rule == "action:trace_proposed"
    assert orch.handle_message(tok, "s\u00ed").policy_rule == "action:trace_opened"

    second_choices = orch.handle_message(tok, "rastrea el otro pago")
    assert second_choices.policy_rule == "action:trace_choose"
    assert "rastreo ya abierto" in second_choices.response_text.lower()
    assert "sin rastreo" in second_choices.response_text.lower()
    assert orch.handle_message(tok, "2").policy_rule == "action:trace_proposed"
    orch.handle_message(tok, "s\u00ed")

    first_again = orch.handle_message(tok, "mu\u00e9strame el rastreo del pago de 40")
    assert first_again.policy_rule == "action:trace_already_open"
    records = stored()
    assert {row["transaction_id"] for row in records} == {"TXN-FIX0006", "TXN-FIX0099"}
    assert len({row["trace_id"] for row in records}) == 2
    assert first_again.verified_facts[0]["result"]["trace_id"] == records[0]["trace_id"]
    queue_path = os.environ["HUMAN_QUEUE_PATH"]
    assert not os.path.exists(queue_path) or open(queue_path, encoding="utf-8").read().strip() == ""


def test_repeated_handoffs_for_the_same_payment_reuse_its_case_but_distinct_payments_do_not(monkeypatch):
    from agent.core import orchestrator as orch_mod
    from agent.tools import account_tools

    real = account_tools.request_trace
    first = real("CLI-FIX0004")["items"][0]
    second = {**first, "transaction_id": "TXN-FIX0099", "amount": 15, "transaction_type": "Payment", "open_trace": None}

    def candidates(customer_id, **filters):
        if filters.get("transaction_id"):
            items = [first if filters["transaction_id"] == first["transaction_id"] else second]
        else:
            items = [first, second]
        return {"items": [{**item, "open_trace": traces.default_traces.find(customer_id, item["transaction_id"])}
                           for item in items]}

    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "request_trace", candidates)
    monkeypatch.setattr(traces.default_traces, "open_verified", lambda *args, **kwargs: None)
    orch, tok, _ = make(*(tool_call_response("request_trace", {}) for _ in range(4)))

    def handoff_for(option):
        assert orch.handle_message(tok, "rastrea mis pagos pendientes").policy_rule == "action:trace_choose"
        assert orch.handle_message(tok, option).policy_rule == "action:trace_proposed"
        return orch.handle_message(tok, "s\u00ed")

    first_case = handoff_for("1")
    first_retry = handoff_for("1")
    second_case = handoff_for("2")
    second_retry = handoff_for("2")
    records = [json.loads(line) for line in open(os.environ["HUMAN_QUEUE_PATH"], encoding="utf-8") if line.strip()]
    assert first_case.ticket_id == first_retry.ticket_id
    assert second_case.ticket_id == second_retry.ticket_id
    assert first_case.ticket_id != second_case.ticket_id
    assert len(records) == 2


def test_a_payment_case_written_without_readback_is_reused_on_the_next_attempt(monkeypatch):
    from agent.core import orchestrator as orch_mod
    from agent.policy import escalation
    from agent.tools import account_tools

    real_request = account_tools.request_trace
    movement = real_request("CLI-FIX0004")["items"][0]
    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "request_trace", lambda customer_id, **kw: {"items": [
        {**movement, "open_trace": traces.default_traces.find(customer_id, movement["transaction_id"])}]})
    monkeypatch.setattr(traces.default_traces, "open_verified", lambda *args, **kwargs: None)
    real_get = escalation.default_queue.get
    readback = {"miss": True}

    def misses_only_first_readback(ticket_id):
        existing = real_get(ticket_id)
        if readback["miss"] and existing is not None:
            readback["miss"] = False
            return None
        return existing

    monkeypatch.setattr(escalation.default_queue, "get", misses_only_first_readback)
    orch, tok, _ = make(tool_call_response("request_trace", {}), tool_call_response("request_trace", {}))

    def try_trace():
        assert orch.handle_message(tok, "rastrea mi transferencia pendiente").policy_rule == "action:trace_proposed"
        return orch.handle_message(tok, "s\u00ed")

    first = try_trace()
    second = try_trace()
    records = [json.loads(line) for line in open(os.environ["HUMAN_QUEUE_PATH"], encoding="utf-8") if line.strip()]
    assert first.ticket_id is None  # the ticket was written but the read-back was unavailable
    assert second.ticket_id == records[0]["ticket_id"]
    assert len(records) == 1
