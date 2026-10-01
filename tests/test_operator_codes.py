"""The texts the operator reads travel as codes with parameters (agent/policy/notes.py), next to the English text they always had."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agent.policy import escalation, notes, router
from agent.policy.router import Decision, Disposition
from agent.tools.errors import DataUnavailable, PermissionDenied, ToolError

ROOT = Path(__file__).resolve().parent.parent
CARD = "4111111111111111"


@pytest.fixture(autouse=True)
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv("HUMAN_QUEUE_PATH", str(tmp_path / "queue.jsonl"))


def filed(decision: Decision, request: str = "necesito ayuda") -> dict:
    ticket = escalation.escalate(decision, "CLI-FIX0004", "ref", request, "es", [], [], [], {}, "trace-1")
    return escalation.default_queue.get(ticket.ticket_id)  # as the console reads it


def every_decision() -> list[Decision]:
    suspended, _ = router.pre_llm("hola", "Suspended")
    unsafe, _ = router.pre_llm("me robaron la tarjeta, es un fraude", "Active")
    return [
        suspended, unsafe, router.foreign_reference(["P-1", "P-2"]), router.llm_unavailable([]), router.turn_timeout(),
        router.after_tool(PermissionDenied("not yours")), router.after_tool(DataUnavailable("no opening date", field="opening_date")),
        router.after_tool(DataUnavailable("nothing to show")), router.after_tool(ToolError("boom")),
        router.after_tool(DataUnavailable("balance missing for product PRD-AB12CD34EF56", field="current_balance")),
        router.trace_step({"items": []}), router.trace_unverified(), router.trace_review("older_than_review_threshold"),
    ]


def test_a_ticket_carries_the_code_of_its_reason_its_questions_and_its_next_step():
    ticket = filed(router.trace_review("older_than_review_threshold"))
    assert ticket["reason_code"] == {"code": "trace_review", "params": {"review_reason": "older_than_review_threshold"}}
    assert ticket["open_question_codes"] == [{"code": "decide_trace", "params": {"review_reason": "older_than_review_threshold"}}]
    assert ticket["next_step_code"] == "trace_review"


def test_the_english_text_stays_as_the_fallback():
    ticket = filed(router.trace_review("older_than_review_threshold"))
    assert ticket["reason"] == "The customer confirmed a trace, but the movement needs a person's approval (older_than_review_threshold)."
    assert ticket["open_questions"] == ["Approve or reject the trace: older_than_review_threshold."]
    assert ticket["suggested_next_step"] == escalation.NEXT_STEP["trace_review"]


def test_every_question_has_its_code_in_the_order_of_the_text_and_the_notes_of_the_evidence_come_last():
    for decision in every_decision():
        ticket = filed(decision)
        assert ticket["reason_code"]["code"] in notes.REASONS
        assert len(ticket["open_question_codes"]) == len(ticket["open_questions"])
        for question, coded in zip(ticket["open_questions"], ticket["open_question_codes"]):
            assert coded is not None and question == notes.QUESTIONS[coded["code"]].format(detail=question.split(": ", 1)[-1], **coded["params"])
        assert ticket["next_step_code"] in {*escalation.NEXT_STEP, "default"}


def test_the_safety_reason_names_the_categories_and_the_lookup_the_field():
    unsafe, _ = router.pre_llm("me robaron la tarjeta, es un fraude", "Active")
    assert filed(unsafe)["reason_code"]["params"]["categories"].split(", ")[0] == unsafe.category
    assert filed(router.after_tool(DataUnavailable("x", field="opening_date")))["open_question_codes"] == [
        {"code": "lookup_field", "params": {"field": "opening_date"}}]
    assert filed(router.after_tool(DataUnavailable("x")))["open_question_codes"][0]["code"] == "lookup_missing_field"


def test_a_category_without_a_next_step_gets_the_default_code_and_text():
    ticket = filed(Decision(Disposition.ESCALATE, "x", "somewhere_new"))
    assert ticket["next_step_code"] == "default" and ticket["suggested_next_step"] == escalation.DEFAULT_NEXT_STEP
    assert ticket["reason_code"] is None  # a plain string has no code: it is shown as written


def test_the_evidence_notes_are_questions_with_a_code_too(monkeypatch):
    monkeypatch.setattr(escalation.account_tools, "recent_activity_for_review", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    unsafe, _ = router.pre_llm("me robaron la tarjeta, es un fraude", "Active")
    ticket = filed(unsafe)
    assert ticket["open_question_codes"][-1] == {"code": "evidence_failed", "params": {"error_type": "RuntimeError"}}
    assert ticket["open_questions"][-1] == "Could not gather recent activity automatically: RuntimeError"


def test_the_parameters_carry_nothing_the_ticket_did_not_already_hold():
    for decision in every_decision():
        ticket = filed(decision, request=f"mi tarjeta {CARD} fue clonada")
        params = json.dumps([ticket["reason_code"], ticket["open_question_codes"]])
        assert CARD not in params and "mi tarjeta" not in params and "CLI-FIX0004" not in params and "trace-1" not in params
        for coded in [ticket["reason_code"], *ticket["open_question_codes"]]:
            assert all(isinstance(v, (str, int)) for v in coded["params"].values())


# The message of an exception can carry internal ids and paths, and it is in English: it stays in the English fallback only.
RAW_MESSAGES = {
    "data_unavailable": DataUnavailable("balance missing for product PRD-AB12CD34EF56", field="current_balance"),
    "data_unavailable_unspecified": DataUnavailable("balance missing for product PRD-AB12CD34EF56"),
    "tool_failure": ToolError('unexpected failure in get_account_summary: OperationalError: IO Error: Cannot open file "C:/srv/data/warehouse/bank.duckdb": Permission denied'),
    "permission_denied": PermissionDenied("customer CLI-FIX0004 does not own product PRD-AB12CD34EF56", resource_id="PRD-AB12CD34EF56"),
}
LEAKS = ("PRD-AB12CD34EF56", "bank.duckdb", "C:/srv", "Cannot open file", "balance missing", "IO Error", "db down")


def wire_params(ticket: dict) -> str:
    return json.dumps([ticket["reason_code"], ticket["open_question_codes"], ticket["next_step_code"]])


def test_the_parameters_carry_no_raw_error_text(monkeypatch):
    for expected_code, error in RAW_MESSAGES.items():
        ticket = filed(router.after_tool(error))
        params = wire_params(ticket)
        assert not any(leak in params for leak in LEAKS), (expected_code, params)
        assert all(isinstance(v, (str, int)) for v in ticket["reason_code"]["params"].values())
    # the code says what happened without the message: the field that is missing, the type of the error
    assert filed(router.after_tool(RAW_MESSAGES["data_unavailable"]))["reason_code"] == {"code": "data_unavailable", "params": {"field": "current_balance"}}
    assert filed(router.after_tool(RAW_MESSAGES["data_unavailable_unspecified"]))["reason_code"] == {"code": "data_unavailable_unspecified", "params": {}}
    assert filed(router.after_tool(RAW_MESSAGES["tool_failure"]))["reason_code"] == {"code": "tool_failure", "params": {"error_type": "ToolError"}}
    assert filed(router.after_tool(RAW_MESSAGES["permission_denied"]))["reason_code"] == {"code": "ownership_check_failed", "params": {}}

    # the evidence that could not be gathered: the database error is not in the code either
    def boom(*a, **k):
        raise RuntimeError('Cannot open file "C:/srv/data/warehouse/bank.duckdb" for product PRD-AB12CD34EF56')
    monkeypatch.setattr(escalation.account_tools, "recent_activity_for_review", boom)
    unsafe, _ = router.pre_llm("me robaron la tarjeta, es un fraude", "Active")
    ticket = filed(unsafe)
    assert not any(leak in wire_params(ticket) for leak in LEAKS)
    assert ticket["open_question_codes"][-1] == {"code": "evidence_failed", "params": {"error_type": "RuntimeError"}}


def test_the_english_fallback_keeps_the_message_of_our_own_errors_and_only_the_type_of_an_unexpected_one():
    ticket = filed(router.after_tool(RAW_MESSAGES["data_unavailable"]))  # a message our code wrote
    assert ticket["reason"] == "Data needed for a verified answer is unavailable: balance missing for product PRD-AB12CD34EF56"
    ticket = filed(router.after_tool(RAW_MESSAGES["tool_failure"]))  # whatever the database or a library said stays out of the ticket
    assert ticket["reason"] == "Tool failure: ToolError" and not any(leak in json.dumps(ticket) for leak in ("bank.duckdb", "C:/srv", "Cannot open file"))


def test_a_ticket_filed_before_the_codes_still_reads_the_same(tmp_path):
    old = {"ticket_id": "t-old", "reason": "Tool failure: boom", "open_questions": ["a"], "suggested_next_step": "b", "customer_id": "C"}
    queue_file = escalation.default_queue.path
    queue_file.write_text(json.dumps(old) + "\n", encoding="utf-8")
    assert escalation.default_queue.get("t-old") == old  # nothing is added on read: the console falls back to the text


# The console has each code in Spanish and Portuguese: a code without its translation would reach the operator in English.
def _translated(language: str) -> str:
    text = (ROOT / f"web/src/i18n/dict/{language}/operator.ts").read_text(encoding="utf-8")
    return text[text.index("  codes: {"):]


@pytest.mark.parametrize("language", ["es", "pt"])
def test_every_code_has_its_translation(language):
    section = _translated(language)
    kinds = {"reason": notes.REASONS, "question": notes.QUESTIONS, "step": {**escalation.NEXT_STEP, "default": ""}}
    for kind, catalog in kinds.items():
        block = re.search(rf"\n    {kind}: \{{(.*?)\n    \}},", section, re.S)
        assert block, f"codes.{kind} is missing in {language}"
        for code in catalog:
            assert re.search(rf"^\s+{code}: ", block.group(1), re.M), f"{language}: codes.{kind}.{code} is not translated"
