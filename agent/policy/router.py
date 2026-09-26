"""Deterministic Decide layer.

This module is intentionally free of any LLM call. It takes the intent/slots
the LLM extracted (agent/llm/*) plus the outcome of any tool calls already
made, and returns one of four dispositions. The LLM proposes; this module
disposes — "permissions and policy [are] enforce[d] outside model-generated
prose," per the challenge brief.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from agent.tools.errors import DataUnavailable, MissingSlot, PermissionDenied, ResourceNotFound

# Intents this workflow (Account/Payment Inquiries) is scoped to automate.
IN_SCOPE_INTENTS = {
    "balance_inquiry",
    "transaction_lookup",
    "payment_status",
    "exchange_rate_inquiry",
}

# Utterance signals that always force escalation regardless of intent,
# because they imply something this workflow must never resolve on its own.
ESCALATION_KEYWORDS = (
    "fraude", "fraudulento", "no reconozco", "no reconocido", "robaron", "robo",
    "clonaron", "clonación", "hackearon", "denuncia", "demanda", "amenaza",
    "suicid", "abuso",
    # Portuguese
    "fraude", "não reconheço", "roubaram", "roubo", "clonaram", "ameaça",
)


class Disposition(str, Enum):
    AUTO_RESOLVE = "AUTO_RESOLVE"
    CLARIFY = "CLARIFY"
    ABSTAIN = "ABSTAIN"
    ESCALATE = "ESCALATE"


@dataclass
class Decision:
    disposition: Disposition
    reason: str
    missing_slots: list[str] = field(default_factory=list)
    verified_facts: dict[str, Any] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)


REQUIRED_SLOTS = {
    "balance_inquiry": [],  # product_id optional: no product => summarize all owned products
    "transaction_lookup": [],
    "payment_status": ["product_id"],
    "exchange_rate_inquiry": ["source_currency", "target_currency"],
}


def contains_escalation_signal(utterance: str) -> bool:
    lowered = utterance.lower()
    return any(kw in lowered for kw in ESCALATION_KEYWORDS)


def decide(
    intent: str,
    slots: dict[str, Any],
    raw_utterance: str,
    ambiguous_product: bool = False,
) -> Decision:
    """Route a classified request. Called BEFORE any tool executes for intents
    that need a disposition first (escalation / out-of-scope / clarification);
    see decide_after_tool_call for the post-execution re-check."""
    if contains_escalation_signal(raw_utterance):
        return Decision(
            disposition=Disposition.ESCALATE,
            reason="Utterance contains a fraud/dispute/safety signal; this workflow does not resolve those.",
            open_questions=["Confirm the customer's account is not compromised.", "Verify identity beyond session token if a human agent proceeds."],
        )

    if intent not in IN_SCOPE_INTENTS:
        return Decision(
            disposition=Disposition.ABSTAIN,
            reason=f"Intent '{intent}' is out of scope for Account/Payment Inquiries.",
        )

    if ambiguous_product:
        return Decision(
            disposition=Disposition.CLARIFY,
            reason="Customer has multiple products and did not specify which one.",
            missing_slots=["product_id"],
        )

    missing = [s for s in REQUIRED_SLOTS.get(intent, []) if not slots.get(s)]
    if missing:
        return Decision(disposition=Disposition.CLARIFY, reason=f"Missing required slot(s): {missing}", missing_slots=missing)

    return Decision(disposition=Disposition.AUTO_RESOLVE, reason="In-scope intent with all required slots present.")


def decide_after_tool_call(intent: str, error: Optional[Exception], result: Any) -> Decision:
    """Re-check after a tool call actually executes. A tool error always wins
    over the pre-call decision — this is the 'Verify' step."""
    if isinstance(error, MissingSlot):
        return Decision(disposition=Disposition.CLARIFY, reason=str(error), missing_slots=list(error.missing_slots))
    if isinstance(error, PermissionDenied):
        return Decision(
            disposition=Disposition.ESCALATE,
            reason="Ownership check failed: customer requested a resource they do not own.",
            open_questions=["Possible unauthorized-access attempt or stale client-side reference; review before responding to customer."],
        )
    if isinstance(error, ResourceNotFound):
        return Decision(disposition=Disposition.CLARIFY, reason="Referenced resource does not exist.", missing_slots=["product_id"])
    if isinstance(error, DataUnavailable):
        return Decision(
            disposition=Disposition.ESCALATE,
            reason=f"Data required to verify an answer is unavailable: {error}",
            open_questions=[str(error)],
        )
    if error is not None:
        return Decision(disposition=Disposition.ESCALATE, reason=f"Unexpected tool failure: {error}", open_questions=["Tool call failed; needs manual lookup."])
    return Decision(disposition=Disposition.AUTO_RESOLVE, reason="Tool call succeeded and result is verified.", verified_facts={"result": result})
