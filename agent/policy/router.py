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
from agent.policy.notes import Note, question, reason
from agent.policy.signals import escalation_categories, normalize
from agent.tools.errors import (
    DataUnavailable,
    MissingSlot,
    NotApplicable,
    PermissionDenied,
    PaymentRuleUnavailable,
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
    reason: str | Note  # a Note carries the code the operator console translates; a plain string is shown as written
    category: str = "none"
    missing_slots: list[str] = field(default_factory=list)
    open_questions: list[str | Note] = field(default_factory=list)
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
        return Decision(Disposition.ESCALATE, reason("compliance_hold"),
                        "compliance_hold", open_questions=[question("confirm_suspension_reason")],
                        rule="customer_status == Suspended"), reading
    cats = escalation_categories(text)
    if cats:
        return Decision(Disposition.ESCALATE, reason("safety_signal", categories=", ".join(cats)), cats[0],
                        open_questions=[question("confirm_block"), question("verify_identity")],
                        rule=f"lexicon:{cats[0]}"), reading
    if reading.escalate and not answering_clarification:
        return Decision(Disposition.ESCALATE,
                        reason("classifier_flag", p=f"{reading.p_escalation:.2f}", threshold=f"{reading.threshold:.2f}"),
                        "classifier_escalation",
                        open_questions=[question("confirm_classifier_signal")],
                        rule="intent_classifier:requires_escalation"), reading
    return None, reading


def foreign_reference(product_ids: list[str]) -> Decision:
    """The message names products owned by another customer (checked in the tool layer, before the model runs)."""
    return Decision(Disposition.ESCALATE, reason("foreign_reference", count=len(product_ids)), "security",
                    open_questions=[question("review_unauthorized_access")],
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
        return Decision(Disposition.ESCALATE, reason("ownership_check_failed"),
                        "security", open_questions=[question("review_unauthorized_access")],
                        rule="tool_error:PermissionDenied")
    if isinstance(error, PaymentRuleUnavailable):
        return Decision(Disposition.ESCALATE, reason("payment_rule_unavailable"), "payment_rule_unavailable",
                        open_questions=[question("confirm_payment_condition")], rule="tool_error:PaymentRuleUnavailable")
    if isinstance(error, DataUnavailable):
        unavailable = reason("data_unavailable", str(error), field=error.field) if error.field else reason("data_unavailable_unspecified", str(error))
        return Decision(Disposition.ESCALATE, unavailable, "data_unavailable",
                        open_questions=[question("lookup_field", field=error.field) if error.field else question("lookup_missing_field")],
                        rule="tool_error:DataUnavailable")
    return Decision(Disposition.ESCALATE, reason("tool_failure", type(error).__name__, error_type=type(error).__name__), "tool_failure",
                    open_questions=[question("manual_check")], rule=f"tool_error:{type(error).__name__}")


def payment_rule_for_agent(result: dict) -> Decision:
    """A reviewed rule covers the condition the customer asked about. Its figures come from the catalog, not from SQL, so the
    customer is not told them: an agent confirms them, with the rule on the ticket (the same category and reply as no rule)."""
    rule = result["rules"][0]
    return Decision(Disposition.ESCALATE, reason("payment_rule_for_agent", rule_id=rule["rule_id"], version=rule["version"]),
                    "payment_rule_unavailable", open_questions=[question("confirm_payment_condition")],
                    rule="payment_rule_for_agent")


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
    return Decision(Disposition.ESCALATE, reason("llm_unavailable"), "llm_unavailable",
                    open_questions=[question("answer_manually_unavailable")], rule="llm_unavailable")


def turn_timeout() -> Decision:
    """The turn's time budget ran out between the model's answer and the lookup: nothing was looked up or done."""
    return Decision(Disposition.ESCALATE, reason("turn_timeout"), "turn_timeout",
                    open_questions=[question("answer_manually_timeout")], rule="turn_timeout")


# --- the one action: tracing a pending movement (D3) ------------------------------------------------------------

_YES = {"si", "sim", "si si", "sim sim", "dale", "ok dale", "si dale", "dale si", "confirmo", "confirmar", "si confirmo",
        "sim confirmo", "ok", "okay", "de acuerdo", "claro", "claro que si", "claro que sim", "si claro", "por supuesto",
        "correcto", "adelante", "hazlo", "sale", "va", "si por favor", "sim por favor", "si quiero", "sim quero",
        "pode ser", "pode", "sim pode", "isso", "yes", "yes please"}
_NO = {"no", "nao", "no no", "nao nao", "no gracias", "nao obrigado", "nao obrigada", "cancelar", "cancela", "cancelalo",
       "mejor no", "no quiero", "nao quero", "no por ahora", "agora nao"}
_ORDINALS = {"primera": 0, "primero": 0, "primer": 0, "primeira": 0, "primeiro": 0, "segunda": 1, "segundo": 1,
             "tercera": 2, "tercero": 2, "terceira": 2, "terceiro": 2, "cuarta": 3, "cuarto": 3, "quarta": 3, "quarto": 3,
             "quinta": 4, "quinto": 4}
_ORDINAL_ANSWER = re.compile(r"^(?:(?:la|el|lo|a|o|numero|nro|opcion|opcao)\s+)*(\w+)$")


def confirmation(text: str) -> str | None:
    """"yes" or "no" when the whole message is a plain answer to a proposed action. Anything else is None and goes
    through the usual checks, so "no, me clonaron la tarjeta" still reaches the safety lexicon. Decided here, never
    by the model: an action happens only on the customer's own yes."""
    plain = " ".join(re.sub(r"[^\w\s]", " ", normalize(text)).split())
    return "yes" if plain in _YES else "no" if plain in _NO else None


def ordinal(text: str, n: int) -> int | None:
    """The index a plain answer to a numbered list picks ("la segunda", "2", "o primeiro"), if the whole message is
    that and the list has it. Resolved in code: the model never saw the list."""
    m = _ORDINAL_ANSWER.match(" ".join(re.sub(r"[^\w\s]", " ", normalize(text)).split()))
    if not m:
        return None
    word = m.group(1)
    index = int(word) - 1 if word.isdigit() else _ORDINALS.get(word)
    return index if index is not None and 0 <= index < n else None


def trace_step(result: dict) -> Decision:
    """What the customer's pending movements that match mean: propose the one, ask which, say it is already open,
    or hand it to a person when nothing of theirs is pending."""
    items = result["items"]
    if not items:
        return Decision(Disposition.ESCALATE, reason("trace_unmatched"),
                        "trace_unmatched", open_questions=[question("check_movement")],
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
    return Decision(Disposition.ESCALATE, reason("trace_unverified"),
                    "trace_unverified", open_questions=[question("open_trace_manually")],
                    rule="action:trace_unverified")


def trace_review(review_reason: str) -> Decision:
    """The customer confirmed, but this movement is old or contradicts their records: a person approves the trace."""
    return Decision(Disposition.ESCALATE, reason("trace_review", review_reason=review_reason),
                    "trace_review", open_questions=[question("decide_trace", review_reason=review_reason)], rule="action:trace_review")


def trace_cancelled() -> Decision:
    return Decision(Disposition.ABSTAIN, "The customer declined the proposed trace; nothing was opened.", "action_cancelled",
                    rule="action:trace_cancelled")
