"""Deterministic Decide/Verify layer — no LLM call anywhere in this module.

The LLM proposes (which tool, which arguments); this module disposes:
- before the LLM runs: compliance holds and safety escalations;
- after each tool call: what the outcome means (see agent/tools/errors.py);
- when the LLM answers without a tool: abstain vs. clarify.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.policy import intent_guard
from agent.policy.signals import escalation_categories, normalize
from agent.tools.errors import (
    DataUnavailable,
    MissingSlot,
    NotApplicable,
    PermissionDenied,
    ResourceNotFound,
)


class Disposition(str, Enum):
    AUTO_RESOLVE = "AUTO_RESOLVE"
    CLARIFY = "CLARIFY"
    ABSTAIN = "ABSTAIN"
    ESCALATE = "ESCALATE"


IN_SCOPE_INTENTS = {"balance_inquiry", "transaction_lookup", "payment_status", "exchange_rate_inquiry"}


@dataclass
class Decision:
    disposition: Disposition
    reason: str
    category: str = "none"
    missing_slots: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    rule: str = ""  # which policy rule fired — shown in traces/tickets as the explanation


def pre_llm(text: str, customer_status: str | None, answering_clarification: bool = False
            ) -> tuple[Decision | None, intent_guard.IntentReading]:
    """Checks that run on raw text before any LLM or tool call, so no
    downstream phrasing can talk them out of firing.

    The classifier guard is skipped when the customer is answering our own
    clarifying question ("la terminada en 3464"): a short, context-dependent
    reply is outside what a per-utterance classifier was trained on (it
    flagged exactly that PT reply as fraud at p=0.70 in the dev workload).
    The safety lexicon still runs on every turn."""
    reading = intent_guard.read(text)
    if customer_status == "Suspended":
        return Decision(Disposition.ESCALATE, "Customer is under an account suspension (compliance hold).",
                        "compliance_hold", open_questions=["Confirm the reason for the suspension before disclosing account data."],
                        rule="customer_status == Suspended"), reading
    cats = escalation_categories(text)
    if cats:
        return Decision(Disposition.ESCALATE, f"Safety signal in the request: {', '.join(cats)}.", cats[0],
                        open_questions=["Confirm whether the customer's card/account must be blocked.",
                                        "Verify identity with a stronger factor before acting."],
                        rule=f"lexicon:{cats[0]}"), reading
    if reading.escalate and not answering_clarification:
        return Decision(Disposition.ESCALATE,
                        f"Intent classifier flags possible fraud/dispute (p={reading.p_escalation:.2f} >= {reading.threshold:.2f}).",
                        "classifier_escalation",
                        open_questions=["Classifier-only signal: confirm with the customer what happened."],
                        rule="intent_classifier:requires_escalation"), reading
    return None, reading


def foreign_reference(product_ids: list[str]) -> Decision:
    """The message names products owned by another customer (checked in the tool layer, before the model runs)."""
    return Decision(Disposition.ESCALATE, f"The request names {len(product_ids)} product(s) owned by another customer.", "security",
                    open_questions=["Possible unauthorized-access or prompt-injection attempt; review the trace."],
                    rule="reference_to_foreign_product")


def after_tool(error: Exception | None) -> Decision | None:
    """None means 'continue': the tool succeeded or the outcome is answerable."""
    if error is None or isinstance(error, NotApplicable):
        return None
    if isinstance(error, MissingSlot):
        return Decision(Disposition.CLARIFY, str(error), "missing_or_invalid_argument",
                        missing_slots=list(error.missing_slots), rule=f"tool_error:{type(error).__name__}")
    if isinstance(error, ResourceNotFound):
        return Decision(Disposition.CLARIFY, str(error), "resource_not_found", missing_slots=["product_id"],
                        rule="tool_error:ResourceNotFound")
    if isinstance(error, PermissionDenied):
        return Decision(Disposition.ESCALATE, "Ownership check failed: the request targets a resource the customer does not own.",
                        "security", open_questions=["Possible unauthorized-access or prompt-injection attempt; review the trace."],
                        rule="tool_error:PermissionDenied")
    if isinstance(error, DataUnavailable):
        return Decision(Disposition.ESCALATE, f"Data needed for a verified answer is unavailable: {error}", "data_unavailable",
                        open_questions=[f"Look up '{error.field or 'the missing field'}' in the core system."],
                        rule="tool_error:DataUnavailable")
    return Decision(Disposition.ESCALATE, f"Tool failure: {error}", "tool_failure",
                    open_questions=["A lookup failed; answer requires a manual check."], rule=f"tool_error:{type(error).__name__}")


def no_tool_answer(reading: intent_guard.IntentReading, text: str) -> Decision:
    """The LLM replied without calling a tool. Nothing was looked up, so this
    is never an automated resolution."""
    if reading.model_available:
        if reading.intent == "out_of_scope":
            return Decision(Disposition.ABSTAIN, "Request is outside account/payment inquiries.", "out_of_scope",
                            rule="intent_classifier:out_of_scope")
        return Decision(Disposition.CLARIFY, "In-scope request without enough information to look anything up.",
                        "needs_clarification", rule=f"intent_classifier:{reading.intent}")
    return Decision(Disposition.CLARIFY if "?" in text else Disposition.ABSTAIN, "classifier unavailable; punctuation fallback",
                    "needs_clarification", rule="fallback:punctuation")


def llm_unavailable(attempts: list[dict[str, Any]]) -> Decision:
    return Decision(Disposition.ESCALATE, "No LLM provider available within the turn budget.", "llm_unavailable",
                    open_questions=["Answer manually; the automated assistant was unavailable."], rule="llm_unavailable")


# --- the one action: tracing a pending movement (D3) ------------------------------------------------------------

_YES = {"si", "sim", "dale", "confirmo", "confirmar", "ok", "okay", "de acuerdo", "claro", "claro que si", "adelante",
        "hazlo", "si por favor", "sim por favor", "si confirmo", "sim confirmo", "si dale", "si quiero", "sim quero",
        "pode ser", "pode", "isso", "yes"}
_NO = {"no", "nao", "no gracias", "nao obrigado", "nao obrigada", "cancelar", "cancela", "cancelalo", "mejor no",
       "no quiero", "nao quero", "no por ahora", "agora nao", "no no"}


def confirmation(text: str) -> str | None:
    """"yes" or "no" when the whole message is a plain answer to a proposed action. Anything else is None and goes
    through the usual checks, so "no, me clonaron la tarjeta" still reaches the safety lexicon. Decided here, never
    by the model: an action happens only on the customer's own yes."""
    plain = " ".join(re.sub(r"[^\w\s]", " ", normalize(text)).split())
    return "yes" if plain in _YES else "no" if plain in _NO else None


def trace_step(result: dict) -> Decision:
    """What the customer's pending movements that match mean: propose the one, ask which, say it is already open,
    or hand it to a person when nothing of theirs is pending."""
    items = result["items"]
    if not items:
        return Decision(Disposition.ESCALATE, "The customer reports a movement that did not arrive, and none of theirs is pending.",
                        "trace_unmatched", open_questions=["Check the movement with payments operations or the sending bank."],
                        rule="action:trace_unmatched")
    if len(items) > 1:
        return Decision(Disposition.CLARIFY, f"{len(items)} pending movements match; the customer picks one.",
                        "missing_or_invalid_argument", missing_slots=["transaction"], rule="action:trace_choose")
    if items[0].get("open_trace"):
        return Decision(Disposition.AUTO_RESOLVE, "A trace is already open for this movement.", "resolved",
                        rule="action:trace_already_open")
    return Decision(Disposition.CLARIFY, "One pending movement matches; waiting for the customer's confirmation.",
                    "confirm_action", rule="action:trace_proposed")


def trace_opened() -> Decision:
    return Decision(Disposition.AUTO_RESOLVE, "The customer confirmed; the trace was opened and read back.", "resolved",
                    rule="action:trace_opened")


def trace_unverified() -> Decision:
    return Decision(Disposition.ESCALATE, "The customer confirmed, but the tracing service did not confirm the trace.",
                    "trace_unverified", open_questions=["Open the trace manually and give the customer its number."],
                    rule="action:trace_unverified")


def trace_cancelled() -> Decision:
    return Decision(Disposition.ABSTAIN, "The customer declined the proposed trace; nothing was opened.", "action_cancelled",
                    rule="action:trace_cancelled")
