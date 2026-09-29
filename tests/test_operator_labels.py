"""Las decisiones del operador, convertidas en etiquetas para revisar el umbral de antigüedad."""
from __future__ import annotations

import pytest

from agent.policy import router
from agent.policy.desk import default_desk
from agent.policy.escalation import escalate
from eval import operator_labels


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var, name in (("HUMAN_QUEUE_PATH", "queue"), ("HUMAN_DESK_PATH", "desk"), ("TRACE_REQUESTS_PATH", "traces")):
        monkeypatch.setenv(var, str(tmp_path / f"{name}.jsonl"))


def ticket(age_days, reason="older_than_review_threshold", with_action=True):
    action = {"tool": "request_trace", "transaction_id": "TXN-FIX0006", "product_id": "PRD-FIX0010", "review_reason": reason,
              "age_days": age_days, "movement": {"transaction_type": "Transfer", "amount": 40, "currency": "USD"}}
    return escalate(router.trace_review(reason), "CLI-FIX0004", "ref", "no llegó", "es", [], [], [], {}, None,
                    action if with_action else None).ticket_id


def decide(ticket_id, action, **kw):
    default_desk.act(ticket_id, "claim", "ana")
    default_desk.act(ticket_id, action, "ana", **kw)


def test_only_decided_tickets_that_carried_an_action_become_labels():
    approved, rejected, open_one, no_action = ticket(100), ticket(100), ticket(100), ticket(100, with_action=False)
    decide(approved, "approve")
    decide(rejected, "reject", reason="fecha incoherente")
    decide(no_action, "release")
    rows = operator_labels.collect()
    assert {r["ticket_id"]: r["decision"] for r in rows} == {approved: "approved", rejected: "rejected"}
    assert open_one not in {r["ticket_id"] for r in rows}
    assert next(r for r in rows if r["decision"] == "rejected")["operator_note"] == "fecha incoherente"


def test_the_sweep_shows_what_each_threshold_would_have_skipped_and_what_it_would_have_let_through():
    decide(ticket(100), "approve")
    decide(ticket(100), "reject")
    decide(ticket(400), "reject")
    s = operator_labels.summarize(operator_labels.collect())
    assert (s["judged"], s["unnecessary_review_rate"]) == (3, 0.333)
    at = {row["threshold_days"]: row for row in s["age_threshold_sweep"]}
    assert (at[90]["reviews_avoided"], at[90]["reviews_still_needed"]) == (0, 3)
    assert (at[180]["reviews_avoided"], at[180]["rejects_that_would_slip_through"], at[180]["reviews_still_needed"]) == (2, 1, 1)
    assert at[180]["of_which_operator_approved"] == 0


def test_no_decisions_is_an_empty_summary_not_a_crash():
    s = operator_labels.summarize(operator_labels.collect())
    assert (s["decided"], s["judged"], s["unnecessary_review_rate"]) == (0, 0, None)
