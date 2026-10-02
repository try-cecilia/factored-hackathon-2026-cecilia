"""The texts an operator reads on a ticket, as stable codes with their parameters.

A ticket carries each of them twice: the English text (what a ticket filed before the codes has, and what a console that does
not know a code shows) and the code, so the console writes it in the operator's language. The English text is rendered from
the catalog here, so the two cannot drift: one line per code, `{name}` marks a parameter.

Parameters are what the text needs and nothing of the customer's: a category, a product count, a review reason, a field name,
the type of error a lookup raised. Never the request, an id, an amount, a card number or the message of an exception: that
message can carry internal ids and is in English whatever the operator reads. The English text takes through `raw` (the
`{detail}` of a catalog line) only what our own code wrote (the message of a DataUnavailable) or the type of an unexpected
error, never what a library or the database said, and the parameters never take it.

To add a text: one line in the catalog of its kind (REASONS, QUESTIONS; the next steps are `escalation.NEXT_STEP`, keyed by
category), and its Spanish and Portuguese in `web/src/i18n/dict/{es,pt}/operator.ts` under `codes`, plus the key in
`web/src/routes/-operator/notes.ts`. `tests/test_operator_codes.py` fails while a code has no translation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REASONS = {
    "compliance_hold": "Customer is under an account suspension (compliance hold).",
    "safety_signal": "Safety signal in the request: {categories}.",
    "classifier_flag": "Intent classifier flags possible fraud/dispute (p={p} >= {threshold}).",
    "foreign_reference": "The request names {count} product(s) owned by another customer.",
    "ownership_check_failed": "Ownership check failed: the request targets a resource the customer does not own.",
    "data_unavailable": "Data needed for a verified answer is unavailable: {detail}",
    "data_unavailable_unspecified": "Data needed for a verified answer is unavailable: {detail}",
    "tool_failure": "Tool failure: {detail}",
    "llm_unavailable": "No LLM provider available within the turn budget.",
    "turn_timeout": "The turn's time budget ran out before the lookup could run.",
    "trace_unmatched": "The customer reports a movement that did not arrive, and none of theirs is pending.",
    "trace_unverified": "The customer confirmed, but the tracing service did not confirm the trace.",
    "trace_review": "The customer confirmed a trace, but the movement needs a person's approval ({review_reason}).",
}

QUESTIONS = {
    "confirm_suspension_reason": "Confirm the reason for the suspension before disclosing account data.",
    "confirm_block": "Confirm whether the customer's card/account must be blocked.",
    "verify_identity": "Verify identity with a stronger factor before acting.",
    "confirm_classifier_signal": "Classifier-only signal: confirm with the customer what happened.",
    "review_unauthorized_access": "Possible unauthorized-access or prompt-injection attempt; review the trace.",
    "lookup_field": "Look up '{field}' in the core system.",
    "lookup_missing_field": "Look up 'the missing field' in the core system.",
    "manual_check": "A lookup failed; answer requires a manual check.",
    "answer_manually_unavailable": "Answer manually; the automated assistant was unavailable.",
    "answer_manually_timeout": "Answer manually; the automated assistant ran out of time.",
    "check_movement": "Check the movement with payments operations or the sending bank.",
    "open_trace_manually": "Open the trace manually and give the customer its number.",
    "decide_trace": "Approve or reject the trace: {review_reason}.",
    "evidence_failed": "Could not gather recent activity automatically: {detail}",
    "evidence_skipped_budget": "Evidence was not gathered: the handoff's time budget was spent.",
    "evidence_skipped_slow": "Evidence was not gathered: it did not finish inside the handoff's time budget, or too many earlier ones are still running.",
}

Params = dict[str, str | int]


@dataclass(frozen=True)
class Note:
    """A text with its code: `text` is the English rendering, `code` and `params` what a console translates."""
    code: str
    text: str
    params: Params = field(default_factory=dict)

    def wire(self) -> dict[str, Any]:
        return {"code": self.code, "params": self.params}


def _note(catalog: dict[str, str], code: str, params: Params, raw: str) -> Note:
    return Note(code, catalog[code].format(detail=raw, **params), params)


def reason(code: str, raw: str = "", **params: str | int) -> Note:
    return _note(REASONS, code, params, raw)


def question(code: str, raw: str = "", **params: str | int) -> Note:
    return _note(QUESTIONS, code, params, raw)


def text_of(item: "str | Note") -> str:
    """The English text of what a decision says: a plain string (no code, as before) or a Note."""
    return item.text if isinstance(item, Note) else item


def wire_of(item: "str | Note | None") -> dict[str, Any] | None:
    """The code and parameters, or None when the text has none (it is shown as written)."""
    return item.wire() if isinstance(item, Note) else None
