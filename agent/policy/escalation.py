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
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent.policy.router import Decision
from agent.policy.signals import PRIORITY_BY_CATEGORY
from agent.tools import account_tools

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


class HumanQueue:
    @property
    def path(self) -> Path:
        p = Path(os.environ.get("HUMAN_QUEUE_PATH", "data/warehouse/human_queue.jsonl"))
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def enqueue(self, ticket: EscalationTicket) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ticket), default=str, ensure_ascii=False) + "\n")

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


default_queue = HumanQueue()

NEXT_STEP = {
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
}
QUEUE = {"fraud": "fraud_ops", "theft": "fraud_ops", "account_takeover": "fraud_ops", "safety": "priority_care",
         "legal_or_regulator": "complaints", "security": "security_review", "compliance_hold": "compliance"}


def _evidence_for(decision: Decision, customer_id: str, actions: list[dict[str, Any]]) -> tuple[list[dict], list[str]]:
    evidence: list[dict] = []
    notes: list[str] = []
    if decision.category in ("fraud", "theft", "account_takeover", "classifier_escalation"):
        try:
            recent = account_tools.recent_activity_for_review(customer_id, limit=10)
            for t in recent["items"]:
                flagged = bool(t["is_fraud"]) or (t["fraud_score"] is not None and t["fraud_score"] >= FRAUD_SCORE_FLAG)
                evidence.append({"type": "transaction", "id": t["transaction_id"], "flagged": flagged,
                                 "detail": {k: t[k] for k in ("transaction_date", "amount", "currency", "merchant_name",
                                                              "transaction_country", "transaction_status", "fraud_score")}})
            evidence.sort(key=lambda e: not e["flagged"])
        except Exception as exc:  # noqa: BLE001 - evidence is best-effort; the ticket must still be filed
            notes.append(f"Could not gather recent activity automatically: {exc}")
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
) -> EscalationTicket:
    evidence, notes = _evidence_for(decision, customer_id, actions)
    ticket = EscalationTicket(
        ticket_id=str(uuid.uuid4()),
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
        reason=decision.reason,
        policy_rule=decision.rule,
        verified_facts=verified_facts,
        evidence=evidence,
        actions_taken=actions,
        open_questions=decision.open_questions + notes,
        suggested_next_step=NEXT_STEP.get(decision.category, "Review and respond to the customer."),
        queue=QUEUE.get(decision.category, "account_payments_l2"),
    )
    default_queue.enqueue(ticket)
    return ticket
