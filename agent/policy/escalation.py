"""Structured human handoff with evidence.

The brief: give the human agent "the request, verified facts, actions taken,
supporting evidence, and unresolved questions" — not a transcript dump. So a
ticket carries: the request and a short list of the customer's prior
requests (not full text), facts verified by tool calls this turn, an
evidence pack gathered deterministically for the escalation category (e.g.
recent transactions with fraud flags for a fraud report), the policy rule
that fired, and open questions. It never carries the session token — only
`session_ref`, a one-way hash.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent.policy.notes import Note, question, text_of, wire_of
from agent.policy.router import Decision
from agent import observability
from agent.filelock import locked
from agent.resilience import (Deadline, RetryPolicy, Saturated, current_handoff, handoff_budget_seconds, handoff_deadline, retry_call,
                              run_bounded)
from agent.resilience import writes as writes_pool
from agent.policy.signals import PRIORITY_BY_CATEGORY
from agent.tools import account_tools

logger = logging.getLogger(__name__)

FRAUD_SCORE_FLAG = 70


@dataclass
class EscalationTicket:
    ticket_id: str
    trace_id: str | None
    created_at: float
    category: str
    priority: str
    customer_id: str
    session_ref: str
    segment: str | None
    country: str | None
    language: str
    request: str
    prior_requests: list[str]
    reason: str
    policy_rule: str
    verified_facts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    actions_taken: list[dict[str, Any]]
    open_questions: list[str]
    suggested_next_step: str
    queue: str = field(default="account_payments_l2")
    # The action an operator may approve (a trace on this movement); empty for tickets that only need a reply.
    pending_action: dict[str, Any] | None = None
    # The codes of the texts above (agent/policy/notes.py), for the console to write them in the operator's language. The English
    # texts stay as they are: tickets filed before these fields have none, and a text without a code is shown as it came.
    reason_code: dict[str, Any] | None = None
    open_question_codes: list[dict[str, Any] | None] = field(default_factory=list)  # one per open question, in its order
    next_step_code: str | None = None


ENQUEUE_RETRY = RetryPolicy(max_attempts=3, base_s=0.1, cap_s=0.5)


class HandoffInFlight(TimeoutError):
    """The ticket's write had begun and did not finish inside the handoff's budget. It is an explicit state, not a ticket: the
    caller names no ticket (only confirmed ones are named), and the write's own outcome, when it comes, is recorded by
    `_record_late`. The customer has the trace code, and the ticket carries the same trace id."""


def _record_late(ticket: "EscalationTicket", error: BaseException | None) -> None:
    """The outcome of a write its caller had stopped waiting for: counted (/admin/capacity, /metrics) and logged by type."""
    kind = "handoff_late_landed" if error is None else "handoff_late_failed"
    observability.count_failure(kind)
    fields = {"trace_id": ticket.trace_id, "kind": kind}
    if error is None:
        logger.info("a handoff write finished after its budget: the ticket exists", extra={"fields": {**fields, "ticket_id": ticket.ticket_id}})
    else:  # no ticket exists, so nothing is named
        logger.error("a handoff write failed after its budget (%s)", type(error).__name__,
                     extra={"fields": {**fields, "error_type": type(error).__name__}})


class HumanQueue:
    @property
    def path(self) -> Path:
        p = Path(os.environ.get("HUMAN_QUEUE_PATH", "data/warehouse/human_queue.jsonl"))
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def enqueue(self, ticket: EscalationTicket) -> None:
        """Append the ticket, retrying a failed write a bounded number of times, all inside the handoff's budget. The ticket
        id is the idempotency key: every attempt looks for the ticket under the lock, so a write that landed but reported
        failure, or a repeated request with the same movement key, is not filed twice. The wait for the lock is what is left
        of the budget, and once it is spent no write begins: a ticket never
        lands after the customer was told it did not. A write that has already begun is not cut off (half a line would be
        worse than a late one): if it outlasts the budget, HandoffInFlight is raised, the write finishes on its own, and its
        outcome is recorded when it does. The write takes a slot of `resilience.writes` until it ends; with none free it is
        refused at once (Saturated) instead of piling up."""
        budget = current_handoff.get() or Deadline(handoff_budget_seconds())
        tries = 0
        state = {"begun": False, "given_up": False, "done": False, "error": None}
        guard = threading.Lock()

        def write() -> None:
            nonlocal tries
            tries += 1
            # Between processes and threads, and never past the budget: the wait for the lock is what is left of it.
            with locked(self.path, timeout=budget.remaining()), open(self.path, "a", encoding="utf-8") as f:
                # A retry or repeated payment handoff checks under the lock first, so a write that already landed is reused.
                if self.get(ticket.ticket_id) is not None:
                    return
                with guard:  # the last look before the write: it begins only if the budget is left and the caller still waits
                    if budget.expired or state["given_up"]:
                        raise TimeoutError("handoff budget spent before the ticket could be written")
                    state["begun"] = True
                f.write(json.dumps(asdict(ticket), default=str, ensure_ascii=False) + "\n")

        def run() -> None:
            error: BaseException | None = None
            try:
                retry_call(write, policy=ENQUEUE_RETRY, idempotency_key=ticket.ticket_id, deadline=budget)
            except BaseException as exc:  # noqa: BLE001 - reported to the caller, or recorded if it stopped waiting
                error = exc
            finally:
                writes_pool.release()
            with guard:
                state.update(done=True, error=error)
                late = state["given_up"] and state["begun"]
            if late:
                _record_late(ticket, error)

        if not writes_pool.try_acquire():
            raise Saturated(f"{writes_pool.limit} ticket writes already in flight")
        worker = threading.Thread(target=run, daemon=True, name="handoff-write")
        worker.start()
        worker.join(max(0.0, budget.remaining()))
        with guard:
            if not state["done"]:
                state["given_up"] = True
                begun = state["begun"]
        if not state["done"]:
            if begun:
                raise HandoffInFlight(f"the write of a ticket for trace {ticket.trace_id} was still running at the deadline")
            raise TimeoutError("handoff budget spent before the ticket could be written")
        if state["error"] is not None:
            raise state["error"]

    def get(self, ticket_id: str) -> dict | None:
        # ponytail: linear scan of a local JSONL file; the bank's case system answers this by id
        if not self.path.exists():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if f'"{ticket_id}"' in line:
                ticket = json.loads(line)
                if ticket.get("ticket_id") == ticket_id:
                    return ticket
        return None

    def for_customer(self, customer_id: str) -> list[dict]:
        """Tickets owned by the authenticated customer, across all of their sessions."""
        if not self.path.exists():
            return []
        # Only the customer's own lines are parsed: this runs on every turn, and the file holds everyone's tickets.
        tickets = (json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if customer_id in line)
        return [ticket for ticket in tickets if ticket["customer_id"] == customer_id]


default_queue = HumanQueue()

NEXT_STEP = {  # by category; the category is the code of the text (`DEFAULT_NEXT_STEP` is "default")
    "fraud": "Call the customer back on the registered number; block the card if confirmed; open a dispute case.",
    "theft": "Block the card/account immediately after identity re-verification; reissue.",
    "account_takeover": "Force credential reset and review recent logins/devices.",
    "safety": "Follow the vulnerable-customer protocol immediately.",
    "legal_or_regulator": "Route to the complaints/legal desk; do not make commitments in the channel.",
    "classifier_escalation": "Confirm with the customer whether they are reporting an unrecognized transaction.",
    "compliance_hold": "Check the suspension reason in the core system before sharing account data.",
    "security": "Review the trace for an unauthorized-access or prompt-injection attempt; do not disclose the requested resource.",
    "data_unavailable": "Look up the missing field in the core system and answer the customer.",
    "tool_failure": "Answer from the core system manually; report the failing lookup.",
    "llm_unavailable": "Answer manually; the assistant was down.",
    "turn_timeout": "Answer manually; the assistant ran out of time before it could look anything up.",
    "trace_unmatched": "Check the movement with payments operations or the sending bank: nothing of the customer's is pending.",
    "trace_unverified": "Open the trace manually and give the customer its number: the tracing service did not confirm it.",
    "trace_review": "Review the movement (see pending_action.review_reason) and approve or reject the trace the customer asked for.",
}
DEFAULT_NEXT_STEP = "Review and respond to the customer."
QUEUE = {"fraud": "fraud_ops", "theft": "fraud_ops", "account_takeover": "fraud_ops", "safety": "priority_care",
         "legal_or_regulator": "complaints", "security": "security_review", "compliance_hold": "compliance",
         "trace_unmatched": "payments_ops", "trace_unverified": "payments_ops", "trace_review": "payments_ops"}


def _evidence_for(decision: Decision, customer_id: str, actions: list[dict[str, Any]]) -> tuple[list[dict], list[Note]]:
    evidence: list[dict] = []
    notes: list[Note] = []
    if decision.category in ("fraud", "theft", "account_takeover", "classifier_escalation"):
        try:
            recent = account_tools.recent_activity_for_review(customer_id, limit=10)
            for t in recent["items"]:
                flagged = bool(t["is_fraud"]) or (t["fraud_score"] is not None and t["fraud_score"] >= FRAUD_SCORE_FLAG)
                evidence.append({"type": "transaction", "id": t["transaction_id"], "flagged": flagged,
                                 "detail": {k: t[k] for k in ("transaction_date", "amount", "currency", "merchant_name",
                                                              "transaction_country", "transaction_status", "fraud_score")}
                                            | {"behavior": t.get("behavior")}})
            evidence.sort(key=lambda e: not e["flagged"])
        except Exception as exc:  # noqa: BLE001 - evidence is best-effort; the ticket must still be filed
            notes.append(question("evidence_failed", type(exc).__name__, error_type=type(exc).__name__))
    for a in actions:
        if a.get("error_type") == "PermissionDenied":
            evidence.append({"type": "denied_request", "id": a.get("args", {}).get("product_id"), "detail": {"tool": a["tool"]}})
    return evidence, notes


def escalate(
    decision: Decision,
    customer_id: str,
    session_ref: str,
    request: str,
    language: str,
    actions: list[dict[str, Any]],
    verified_facts: list[dict[str, Any]],
    prior_requests: list[str],
    attributes: dict,
    trace_id: str | None,
    pending_action: dict[str, Any] | None = None,
    ticket_id: str | None = None,
) -> EscalationTicket:
    with handoff_deadline() as budget:
        if budget.expired:  # best-effort by design, and never worth more time than the handoff has
            evidence, notes = [], [question("evidence_skipped_budget")]
        else:
            try:  # a read: bounded, and left to finish in the background if it runs over
                evidence, notes = run_bounded(lambda: _evidence_for(decision, customer_id, actions), budget.remaining() / 2)  # never more than half: the write comes next
            except TimeoutError:
                evidence, notes = [], [question("evidence_skipped_slow")]
        return _file(decision, customer_id, session_ref, request, language, actions, verified_facts, prior_requests, attributes,
                     trace_id, pending_action, evidence, notes, ticket_id)


def _file(decision, customer_id, session_ref, request, language, actions, verified_facts, prior_requests, attributes, trace_id,
          pending_action, evidence, notes, ticket_id: str | None = None) -> EscalationTicket:
    questions = [*decision.open_questions, *notes]
    ticket = EscalationTicket(
        ticket_id=ticket_id or str(uuid.uuid4()),
        trace_id=trace_id,
        created_at=time.time(),
        category=decision.category,
        priority=PRIORITY_BY_CATEGORY.get(decision.category, "High" if decision.category == "security" else "Medium"),
        customer_id=customer_id,
        session_ref=session_ref,
        segment=attributes.get("segment"),
        country=attributes.get("country"),
        language=language,
        request=request[:500],
        prior_requests=[p[:160] for p in prior_requests[-3:]],
        reason=text_of(decision.reason),
        policy_rule=decision.rule,
        verified_facts=verified_facts,
        evidence=evidence,
        actions_taken=actions,
        open_questions=[text_of(q) for q in questions],
        suggested_next_step=NEXT_STEP.get(decision.category, DEFAULT_NEXT_STEP),
        queue=QUEUE.get(decision.category, "account_payments_l2"),
        pending_action=pending_action,
        reason_code=wire_of(decision.reason),
        open_question_codes=[wire_of(q) for q in questions],
        next_step_code=decision.category if decision.category in NEXT_STEP else "default",
    )
    default_queue.enqueue(ticket)
    return ticket
