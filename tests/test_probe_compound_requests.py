"""The live probe for two requests in one message, run offline with scripted models (no key, no network).

What is tested is the probe itself: its oracle, its grading (a half answer never counts), its isolation from a running app, its
resume and budget, and its report. What a live model does with the cases is what it exists to find out.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from agent.llm.client import LLMResponse, LLMUnavailable, Usage
from ops import probe_compound_requests as probe

CASES = probe.load_jsonl(probe.CASES)
SEQUENCES = probe.load_jsonl(probe.SEQUENCES)
BY_TEXT = {c["text"]: c for c in CASES} | {t: {"reads": s["reads"], "kind": "sequence"} for s in SEQUENCES for t in s["turns"][:1]}


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    with probe.probe_environment(tmp_path_factory.mktemp("probe")) as directory:
        yield directory


def call_for(need: dict) -> tuple[str, dict]:
    """The tool call a model that understood the request makes for one read of the answer key."""
    args = {k: v for k, v in need.items() if k not in ("tool", "product")}
    if need.get("product"):
        args["product_id"] = need["product"]
    if need["tool"] == "get_payment_status" and "product_id" not in args:
        args["product_id"] = "Tarjeta Crédito"
    return need["tool"], args


@dataclass
class Scripted:
    """A model that answers each request with `how(reads)`: all the reads, only the first, or none."""
    how: object = staticmethod(lambda reads: reads)
    calls: int = 0

    def chat(self, messages, tools=None, temperature=0.0):
        self.calls += 1
        text = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        reads = BY_TEXT[text]["reads"] if text in BY_TEXT else []  # a follow-up ("te pedí dos cosas") is not in the table: nothing
        chosen = self.how(reads)
        return LLMResponse(content=None, provider="scripted", model="scripted", latency_ms=1.0, usage=Usage(100, 10), attempts=[{}],
                           tool_calls=[{"id": f"c{i}", "name": n, "arguments": json.dumps(a)} for i, (n, a) in enumerate(map(call_for, chosen))])


class Down:
    def chat(self, messages, tools=None, temperature=0.0):
        raise LLMUnavailable("down", [{"provider": "x", "outcome": "error"}])


def run(client, environment, **kw):
    out_path = kw.pop("out_path", None)
    cfg = probe.Config(**{"model_name": "scripted:scripted", "repeats": 1, "pace_seconds": 0, **kw})
    return probe.run(cfg, client, CASES, SEQUENCES, out_path, sleep=lambda s: None, announce=lambda m: None)


# --- the cases and the answer key ----------------------------------------------------------------------------------------------

def test_the_cases_are_sixteen_in_eight_families_in_both_languages_and_four_sequences():
    assert len(CASES) == 16 and len({c["family"] for c in CASES}) == 8 and {c["language"] for c in CASES} == {"es", "pt"}
    assert sorted({c["kind"] for c in CASES}) == ["control", "double", "trace", "triple"]
    assert [len(c["reads"]) for c in CASES if c["kind"] == "double"] == [2] * 8 and [len(c["reads"]) for c in CASES if c["kind"] == "triple"] == [3] * 4
    assert len(SEQUENCES) == 4 and all(len(s["turns"]) == 3 for s in SEQUENCES)
    assert len({c["id"] for c in CASES}) == 16


def test_no_phrase_of_the_probe_is_in_the_prompt_the_model_is_given():
    from agent.llm import prompts

    # The follow-ups ("te pedí dos cosas", "¿y las últimas 5?") are the plan's own examples of the recovery rule; the requests are not.
    for text in [c["text"] for c in CASES] + [s["turns"][0] for s in SEQUENCES]:
        assert text.lower() not in prompts.SYSTEM_PROMPT.lower(), text


def test_the_oracle_computes_the_answer_key_with_its_own_sql_and_agrees_with_the_tools(environment):
    from agent.tools import account_tools, db

    con = db.get_connection()
    transfers = probe.oracle(con, {"tool": "list_transactions", "transaction_type": "Transfer", "limit": 5})
    assert transfers["ids"] == ["TXN-FIX0117", "TXN-FIX0116", "TXN-FIX0115", "TXN-FIX0106", "TXN-FIX0105"]  # the latest of the two accounts
    tool = account_tools.list_transactions(probe.CUSTOMER, transaction_type="Transfer", limit=5)["items"]
    assert [t["transaction_id"] for t in tool] == transfers["ids"]
    checking = probe.oracle(con, {"tool": "list_transactions", "transaction_type": "Transfer", "limit": 5, "product": "Cuenta Corriente"})
    assert checking["ids"] == ["TXN-FIX0115", "TXN-FIX0106", "TXN-FIX0105", "TXN-FIX0104", "TXN-FIX0103"] and checking["args"]["product_id"] == "PRD-FIX0015"
    assert probe.oracle(con, {"tool": "list_transactions", "transaction_type": "Payment", "status": "Pending"})["ids"] == ["TXN-FIX0113"]
    assert probe.oracle(con, {"tool": "get_payment_status", "product": "Tarjeta Crédito"})["days_past_due"] == 90
    assert probe.oracle(con, {"tool": "get_account_summary"})["ids"] == ["PRD-FIX0015", "PRD-FIX0016", "PRD-FIX0017"]


# --- a model that understands, a model that gives half, a model that is down ---------------------------------------------------

def test_a_model_that_asks_for_every_read_covers_every_case_and_the_composition_is_exact(environment):
    rows = run(Scripted(), environment)
    assert len(rows) == 16 + 60  # the cases once, and the 4 sequences of 3 turns, 5 times each
    cases = [r for r in rows if r["kind"] != "sequence"]
    assert all(r["covered"] and r["declared_all"] for r in cases if r["kind"] != "triple")
    assert all(not r["unsafe"] and r["records_sent"] == 0 and r["trace_opened"] == 0 for r in cases)
    assert all(r["composition_exact"] for r in cases if r["kind"] in ("double", "control"))
    triple = [r for r in cases if r["kind"] == "triple"]
    assert all(r["declared_all"] and not r["covered"] and r["composition_exact"] for r in triple)  # cap 2: the third is named, not read
    assert {r["policy_rule"] for r in cases if r["kind"] == "trace"} == {"action:trace_proposed"}
    assert all(r["model_served"] == "scripted/scripted" and r["llm_calls"] == 1 and r["attempts"] == 1 for r in cases)


def test_a_half_answer_never_counts_even_when_the_turn_ended_as_a_resolution(environment):
    rows = [r for r in run(Scripted(how=lambda reads: reads[:1]), environment, only="double")]
    assert len(rows) == 8 and all(r["disposition"] == "AUTO_RESOLVE" and not r["covered"] and not r["declared_all"] for r in rows)
    assert all(len(r["missing"]) == 1 for r in rows)


def test_what_the_model_asks_for_with_the_wrong_filter_does_not_cover_the_read(environment):
    from agent.tools import db

    case = next(c for c in CASES if c["id"] == "balance_transfers.es")
    wrong = {"disposition": "AUTO_RESOLVE", "verified_facts": [], "response_text": "", "policy_rule": "verified_tool_results"}
    from agent.tools import account_tools

    def fact(**args):
        return {"tool": "list_transactions", "args": args, "result": account_tools.list_transactions(probe.CUSTOMER, **args)}

    con = db.get_connection()
    need = {"tool": "list_transactions", "transaction_type": "Transfer", "limit": 5}
    assert probe.fact_covers(con, need, [fact(transaction_type="Transfer", limit=5)])
    assert not probe.fact_covers(con, need, [fact(limit=5)])  # any 5 movements
    assert not probe.fact_covers(con, need, [fact(transaction_type="Transfer", limit=3)])  # the wrong quantity
    assert not probe.fact_covers(con, need, [fact(transaction_type="Transfer", limit=5, product_id="PRD-FIX0015")])  # one account only: other reads
    assert not probe.fact_covers(con, need, [fact(transaction_type="Payment", limit=5)])
    assert not probe.fact_covers(con, need, [])
    assert case and wrong


def test_a_reply_that_is_not_what_the_templates_give_is_not_an_exact_composition(environment):
    from types import SimpleNamespace

    from agent.tools import account_tools, db

    con = db.get_connection()
    case = next(c for c in CASES if c["id"] == "balance_transfers.es")
    facts = [{"tool": "get_account_summary", "args": {}, "result": account_tools.get_account_summary(probe.CUSTOMER)}]
    from agent.core import render
    from agent.core.orchestrator import with_aliases

    text = render.render_answer(facts, "es", with_aliases(account_tools.get_customer_profile(probe.CUSTOMER)["products"]))
    declared = [{"tool": "get_account_summary"}]

    def verdict(reply):
        result = SimpleNamespace(disposition="AUTO_RESOLVE", verified_facts=facts, response_text=reply, policy_rule="verified_tool_results")
        return probe.judge(con, case, result, declared, 2)["composition_exact"]

    assert verdict(text) is True
    assert verdict(text + " Gracias por tu paciencia.") is False  # an arbitrary suffix
    assert verdict(text.replace("5,000.00", "5,001.00")) is False  # a figure that is not the read's
    assert verdict("Quedó sin atender: transferencias.\n" + text) is False  # a false notice


def test_a_model_that_is_down_is_recorded_as_down_and_nothing_is_counted_as_covered(environment):
    rows = run(Down(), environment, only="control")
    assert len(rows) == 2 and all(r["model_down"] and not r["covered"] and r["llm_calls"] == 0 or r["model_down"] for r in rows)
    assert all(not r["covered"] and r["error_type"] == "LLMUnavailable" for r in rows)


# --- the run: isolation, the cap, resume and budget ------------------------------------------------------------------------------

def test_the_cap_is_changed_inside_the_run_only_and_the_triple_is_answered_with_three(environment):
    from agent.core import orchestrator

    assert orchestrator.MAX_TOOL_CALLS_PER_TURN == 2
    rows = run(Scripted(), environment, only="triple", cap=3)
    assert len(rows) == 4 and all(r["covered"] and r["cap"] == 3 and r["composition_exact"] and len(r["executed"]) == 3 for r in rows)
    assert orchestrator.MAX_TOOL_CALLS_PER_TURN == 2  # the product's default is not touched


def test_the_probe_writes_in_its_own_directory_and_the_environment_comes_back(tmp_path):
    before = {k: os.environ.get(k) for k in ("DUCKDB_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH", "HUMAN_QUEUE_PATH", "STATE_DB_PATH")}
    with probe.probe_environment(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path) as directory:
        assert os.environ["AUDIT_LOG_PATH"].startswith(str(directory)) and os.environ["DUCKDB_PATH"].startswith(str(directory))
        run(Scripted(), directory, only="control")
        assert (directory / "audit.jsonl").exists()
    assert {k: os.environ.get(k) for k in before} == before


def test_a_run_resumes_by_its_id_without_repeating_a_turn(environment, tmp_path):
    out = tmp_path / "rows.jsonl"
    first = run(Scripted(), environment, only="control", run_id="r1", out_path=out)
    again = run(Scripted(), environment, only="control", run_id="r1", out_path=out)
    other = run(Scripted(), environment, only="control", run_id="r2", out_path=out)
    assert len(first) == 2 and again == [] and len(other) == 2
    assert len(out.read_text().splitlines()) == 4


def test_the_budget_stops_the_run_and_a_call_with_no_known_price_is_not_counted_as_free(environment):
    rows = run(Scripted(), environment, only="control", repeats=5, budget_usd=0.03)  # the scripted model has no price: USD 0.02 each
    assert len(rows) == 2 and all(r["cost_usd"] is None for r in rows)


def test_a_row_holds_no_secret_header_or_raw_answer_and_names_what_was_measured(environment):
    row = run(Scripted(), environment, only="control")[0]
    text = json.dumps(row)
    assert not any(w in text.lower() for w in ("api_key", "authorization", "failed_generation", "reasoning"))
    for key in ("run_id", "commit", "prompt_version", "prompt_sha", "schemas_sha", "cases_sha", "fingerprint", "model_requested", "model_served", "cap",
                "declared", "executed", "tokens", "total_ms", "llm_ms", "attempts"):
        assert key in row, key


def test_a_sequence_is_scored_by_recovery_and_its_first_turn_is_the_request(environment):
    rows = run(Scripted(how=lambda reads: reads[:1]), environment, only="sequences")
    assert len(rows) == 4 * 5 * 3 and {r["turn"] for r in rows} == {0, 1, 2}
    first = [r for r in rows if r["turn"] == 0]
    assert all(not r["covered"] for r in first)  # the half answer is an opportunity for recovery


# --- the report and the command -------------------------------------------------------------------------------------------------

def test_the_report_applies_the_preregistered_thresholds(environment):
    good = probe.report(run(Scripted(), environment, repeats=10, only="double") + run(Scripted(), environment, repeats=10, only="control"))
    assert "| 2. two-request cases" in good and "MET" in good.split("2. two-request cases")[1].splitlines()[0] and "NOT MET" not in good.split("2. two-request cases")[1].splitlines()[0]
    half = probe.report(run(Scripted(how=lambda reads: reads[:1]), environment, repeats=10, only="double"))
    assert "NOT MET" in half.split("2. two-request cases")[1].splitlines()[0]
    assert "[" in good and "%]" in good  # Wilson intervals beside the rates


def test_the_dry_run_counts_the_turns_and_the_cost_without_calling_anything(capsys):
    assert probe.main(["--dry-run", "--models", "anthropic:claude-sonnet-5,groq:openai/gpt-oss-120b", "--repeats", "10"]) == 0
    out = capsys.readouterr().out
    assert "anthropic:claude-sonnet-5: 220 turns" in out and "groq:openai/gpt-oss-120b: 220 turns" in out  # 16 x 10 and 4 x 5 x 3


def test_the_report_command_reads_a_rows_file(environment, tmp_path, capsys):
    out = tmp_path / "rows.jsonl"
    run(Scripted(), environment, only="double", out_path=out)
    assert probe.main(["--report", str(out)]) == 0
    assert "scripted/scripted" in capsys.readouterr().out


def test_the_documented_commands_parse():
    import re

    doc = probe.__doc__
    commands = re.findall(r"python -m ops\.probe_compound_requests (.*?)(?: \\\\\n\s+(.*?))?(?:\s+#|\n)", doc)
    assert len(commands) >= 5 and "--models" in doc and "--cap 3" in doc and "--dry-run" in doc


def test_a_run_where_no_model_answered_reports_that_and_no_criterion_as_met(environment):
    text = probe.report(run(Down(), environment, only="control"))
    assert "no model answered" in text and "MET" not in text.replace("NOT MET", "")
