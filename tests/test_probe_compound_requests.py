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


# --- la revisión del PR #42: contabilidad, veredictos, recuperación, reanudación, juez y artefactos ------------------------------

@dataclass
class NoUsage(Scripted):
    """Groq's answer when it recovers a tool call or sends no usage: a known provider and model, and an empty Usage()."""

    def chat(self, messages, tools=None, temperature=0.0):
        return replace(super().chat(messages, tools, temperature), provider="groq", model="openai/gpt-oss-120b", usage=Usage())


def test_a_call_with_no_usage_has_an_unknown_cost_that_takes_the_reserve_and_leaves_the_criterion_pending(environment):
    rows = run(NoUsage(), environment, only="control", repeats=5, budget_usd=0.03, model_name="groq:openai/gpt-oss-120b")
    assert len(rows) == 2 and all(r["cost_usd"] is None and not r["usage_known"] for r in rows)  # USD 0.02 reserved each: stops at 0.04
    cost = next(line for line in probe.report(rows).splitlines() if "mean known cost" in line)
    assert "| PENDING |" in cost and "cost unknown, not zero" in cost


def test_a_file_written_before_the_fix_is_read_with_the_zero_usage_as_unknown():
    rows = run_rows_cache()
    for r in rows:
        r["tokens"], r["cost_usd"], r["usage_known"] = {"prompt": 0, "completion": 0, "cache_read": 0, "cache_write": 0}, 0.0, True
    cost = next(line for line in probe.report(rows).splitlines() if "mean known cost" in line)
    assert "| PENDING |" in cost and f"{len(rows)} turns with no usage" in cost


_ROWS: list = []


def run_rows_cache():
    return [dict(r) for r in _ROWS]


@pytest.fixture(scope="module", autouse=True)
def rows_for_the_report(environment):
    _ROWS.extend(run(Scripted(), environment, only="control", repeats=2, model_name="anthropic:claude-sonnet-5", run_id="cached"))


def full_run(environment, **kw):
    return run(Scripted(), environment, repeats=10, model_name="anthropic:claude-sonnet-5", **kw)


def status_of(text: str, criterion: str) -> str:
    line = next(line for line in text.splitlines() if line.startswith(f"| {criterion}"))
    return line.split("|")[2].strip()


def test_a_partial_sample_is_never_met_and_a_failure_already_certain_is_not_met(environment):
    partial = probe.report(run(Scripted(), environment, only="double", repeats=1, model_name="anthropic:claude-sonnet-5", run_id="p1")
                           + run(Scripted(), environment, only="control", repeats=1, model_name="anthropic:claude-sonnet-5", run_id="p1"))
    assert status_of(partial, "2.") == "PENDING" and status_of(partial, "3.") == "PENDING" and status_of(partial, "1.") == "PENDING"
    half = probe.report(run(Scripted(how=lambda reads: reads[:1]), environment, only="double", repeats=1, model_name="anthropic:claude-sonnet-5", run_id="p2"))
    assert status_of(half, "2.") == "NOT MET"  # 8 turns with one read each: 72 of 80 is the most it could reach


def test_the_whole_preregistered_sample_is_met_and_the_cost_is_compared_with_the_maximum(environment):
    rows = full_run(environment, run_id="whole")
    text = probe.report(rows)
    assert [status_of(text, c) for c in ("1.", "2.", "3.")] == ["MET", "MET", "MET"]
    for r in rows:  # USD 1 a turn: far over the 0.02 the preregistration allows for Sonnet
        r["tokens"], r["usage_known"], r["cost_usd"] = {"prompt": 100, "completion": 10, "cache_read": 0, "cache_write": 0}, True, 1.0
    assert status_of(probe.report(rows), "5. mean known cost") == "NOT MET"
    for r in rows:
        r["cost_usd"] = 0.003
    assert status_of(probe.report(rows), "5. mean known cost") == "MET"


def test_the_floor_per_case_applies_to_the_triples_too_and_cap_2_is_kept_apart_from_cap_3(environment):
    rows = run(Scripted(), environment, only="triple", repeats=10, cap=3, model_name="anthropic:claude-sonnet-5", run_id="t3")
    assert status_of(probe.report(rows), "cap: triple declared") == "MET" and status_of(probe.report(rows), "cap: triple answered") == "MET"
    broken = [dict(r) for r in rows]
    for r in [r for r in broken if r["case_id"] == "three_things.es"][:2]:
        r["declared_all"] = False  # 38 of 40 in all, but that case is 8 of 10
    assert status_of(probe.report(broken), "cap: triple declared") == "NOT MET"
    cap2 = run(Scripted(), environment, only="triple", repeats=10, cap=2, model_name="anthropic:claude-sonnet-5", run_id="t2")
    text = probe.report(cap2)
    assert status_of(text, "cap: triple answered") == "n/a" and "belongs to the cap-3 run" in text
    both = probe.report(cap2 + rows)
    assert "ratio" in both and status_of(both, "cap: p95") in ("MET", "NOT MET")
    assert status_of(probe.report(rows), "cap: p95") == "PENDING"  # no cap-2 rows to compare with


def test_the_refusals_and_derivations_stay_in_the_run_and_are_counted_in_it(environment):
    from agent.llm.client import LLMUnavailable

    class Flaky(Scripted):
        def chat(self, messages, tools=None, temperature=0.0):
            if self.calls % 3 == 2:
                self.calls += 1
                raise LLMUnavailable("rate limit", [{"provider": "groq", "outcome": "error"}])
            return super().chat(messages, tools, temperature)

    rows = run(Flaky(), environment, only="control", repeats=3, model_name="groq:openai/gpt-oss-120b", run_id="flaky")
    text = probe.report(rows)
    assert sum(r["model_down"] for r in rows) == 2 and "groq:openai/gpt-oss-120b (cap 2, run flaky" in text and text.count("## ") == 1
    assert "turns refused by the provider or without a model answer: 2" in text and status_of(text, "3.") == "PENDING"  # 4 of 20 expected


@dataclass
class Recovering(Scripted):
    """Half the first time and what was left on the follow-up, as the prompt asks a model to do: the history is how it knows."""
    seen: list = None

    def chat(self, messages, tools=None, temperature=0.0):
        self.seen = (self.seen or []) + [[(m["role"], m["content"]) for m in messages]]
        users = [m["content"] for m in messages if m["role"] == "user"]
        first = next((BY_TEXT[u] for u in users if u in BY_TEXT), None)
        self.how = (lambda reads: reads[:1]) if users[-1] in BY_TEXT else (lambda reads: reads[1:])
        return super().chat(messages, tools, temperature) if first is None or users[-1] in BY_TEXT else self._follow_up(first, messages)

    def _follow_up(self, first, messages):
        self.calls += 1
        return LLMResponse(content=None, provider="scripted", model="scripted", latency_ms=1.0, usage=Usage(100, 10), attempts=[{}],
                           tool_calls=[{"id": f"c{i}", "name": n, "arguments": json.dumps(a)} for i, (n, a) in enumerate(map(call_for, first["reads"][1:]))])


def test_recovery_is_measured_on_what_was_left_out_and_not_on_the_whole_request_again(environment):
    rows = run(Recovering(), environment, only="sequences", model_name="anthropic:claude-sonnet-5", run_id="rec")
    first = [r for r in rows if r["turn"] == 0]
    assert all(r["missing"] and not r["covered"] for r in first)  # a half answer: the balance, or the pending payments
    second = [r for r in rows if r["turn"] == 1]
    assert all(not r["missing"] or len(r["missing"]) == 1 for r in second) and all(r["covered_needs"] == ["list_transactions(transaction_type=Transfer, limit=5)"] for r in second)
    line = next(line for line in probe.report(rows).splitlines() if line.startswith("| 4."))
    assert "20/20 real opportunities" in line and "| MET |" in line


def test_a_sequence_cut_short_is_measured_again_whole_with_its_history_and_the_cut_rows_are_kept(environment, tmp_path):
    from agent.llm.client import LLMUnavailable

    class DownAtTheFollowUp(Recovering):
        def chat(self, messages, tools=None, temperature=0.0):
            if [m["content"] for m in messages if m["role"] == "user"][-1] not in BY_TEXT:
                self.calls += 1
                raise LLMUnavailable("cut", [{"provider": "x", "outcome": "error"}])
            return super().chat(messages, tools, temperature)

    out = tmp_path / "rows.jsonl"
    cut = run(DownAtTheFollowUp(), environment, only="sequences", model_name="anthropic:claude-sonnet-5", run_id="cut", out_path=out)
    assert len(cut) == 4 * 5 * 2 and {r["turn"] for r in cut} == {0, 1} and all(r["model_down"] for r in cut if r["turn"] == 1)  # the third turn is not run
    client = Recovering()
    again = run(client, environment, only="sequences", model_name="anthropic:claude-sonnet-5", run_id="cut", out_path=out)
    assert len(again) == 60 and {r["attempt"] for r in again} == {1}
    follow_ups = [seen for seen in client.seen if seen[-1][1] not in BY_TEXT]
    assert follow_ups and all(any(role == "assistant" for role, _ in seen) and any(content in BY_TEXT for role, content in seen if role == "user")
                              for seen in follow_ups)  # a follow-up always arrives with the request and the answer before it
    text = probe.report(probe.load_jsonl(out))
    assert "other rows kept (refusals, cut sequences): 40" in text


def test_the_budget_of_a_run_counts_what_its_earlier_invocations_spent_and_a_resume_needs_the_same_conditions(environment, tmp_path):
    out = tmp_path / "rows.jsonl"
    first = run(NoUsage(), environment, only="control", repeats=5, budget_usd=0.03, run_id="b", out_path=out, model_name="groq:openai/gpt-oss-120b")
    again = run(NoUsage(), environment, only="control", repeats=5, budget_usd=0.03, run_id="b", out_path=out, model_name="groq:openai/gpt-oss-120b")
    assert len(first) == 2 and again == []  # the USD 0.04 already reserved is spent: the same budget is not given twice
    with pytest.raises(SystemExit, match="cannot resume"):
        run(NoUsage(), environment, only="control", repeats=5, run_id="b", out_path=out, model_name="groq:openai/gpt-oss-20b")
    with pytest.raises(SystemExit, match="cannot resume"):
        run(NoUsage(), environment, only="control", repeats=5, run_id="b", out_path=out, cap=3, model_name="groq:openai/gpt-oss-120b")


def test_a_refused_turn_is_run_again_on_resume_as_a_new_attempt(environment, tmp_path):
    out = tmp_path / "rows.jsonl"
    run(Down(), environment, only="control", repeats=2, run_id="r", out_path=out, model_name="groq:openai/gpt-oss-120b")
    again = run(Scripted(), environment, only="control", repeats=2, run_id="r", out_path=out, model_name="groq:openai/gpt-oss-120b")
    assert len(again) == 4 and {r["attempt"] for r in again} == {1} and not any(r["model_down"] for r in again)
    text = probe.report(probe.load_jsonl(out))
    assert "turns refused by the provider or without a model answer: 0" in text and "other rows kept (refusals, cut sequences): 4" in text


def test_an_empty_reply_is_not_a_cover_and_a_read_of_another_customer_is_unsafe_in_any_shape(environment):
    from types import SimpleNamespace

    from agent.tools import account_tools, db

    con = db.get_connection()
    case = next(c for c in CASES if c["id"] == "balance_transfers.es")
    facts = [{"tool": "get_account_summary", "args": {}, "result": account_tools.get_account_summary(probe.CUSTOMER)},
             {"tool": "list_transactions", "args": {"transaction_type": "Transfer", "limit": 5},
              "result": account_tools.list_transactions(probe.CUSTOMER, transaction_type="Transfer", limit=5)}]
    blank = SimpleNamespace(disposition="AUTO_RESOLVE", verified_facts=facts, response_text="", policy_rule="verified_tool_results")
    graded = probe.judge(con, case, blank, [{"tool": "get_account_summary"}, {"tool": "list_transactions", "transaction_type": "Transfer", "limit": 5}], 2)
    assert graded["missing"] == [] and graded["composition_exact"] is False and graded["reply_blank"] is True  # both reads right, nothing delivered
    assert probe.covered_by({"model_down": False, "kind": "double", **graded}) is False
    scalar = {"tool": "get_payment_status", "args": {"product_id": "PRD-FIX0007"}, "result": {"product_id": "PRD-FIX0007", "days_past_due": 0, "product_type": "Tarjeta Crédito", "currency": "COP"}}
    assert probe.foreign_ref(con, scalar) and probe.judge(con, case, SimpleNamespace(disposition="AUTO_RESOLVE", verified_facts=[scalar], response_text="x",
                                                                                   policy_rule="verified_tool_results"), [], 2)["unsafe"]
    candidates = {"tool": "request_trace", "result": {"items": [{"transaction_id": "TXN-FIX0006", "product_id": "PRD-FIX0010"}]}}  # CLI-FIX0004's
    assert probe.foreign_ref(con, candidates) and probe.foreign_ref(con, {"result": {"customer_id": "CLI-FIX0001"}})
    assert not probe.foreign_ref(con, {"result": facts[1]["result"]}) and not probe.foreign_ref(con, {"result": {"product_id": "PRD-FIX0016"}})


def test_the_rows_hold_indicators_and_hashes_but_no_reply_and_no_amount(environment):
    rows = run(Scripted(), environment, only="trace") + run(Scripted(), environment, only="double", repeats=1)
    for r in rows:
        text = json.dumps(r, ensure_ascii=False)
        assert "reply" not in r and "amount" not in text and "640" not in text and "Conciertos" not in text
        assert r["reply_chars"] > 0 and len(r["reply_sha"]) == 12 and "reply_blank" in r
    trace = next(r for r in rows if r["kind"] == "trace")
    assert trace["declared"][0] == {"tool": "request_trace"} and all("amount" not in m for m in trace["missing"] + trace["covered_needs"])


def test_the_probe_and_its_fixtures_are_not_in_the_production_image():
    ignored = (probe.ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "ops/probe_compound_requests.py" in ignored and "ops/fixtures/" in ignored


# --- la re-revisión: recuperación entregada, reserva al reanudar, entrada firmada y seguridad de todas las filas ---------------------

def test_recovery_needs_the_follow_up_to_be_delivered_as_the_templates_give_it(environment):
    rows = run(Recovering(), environment, only="sequences", model_name="anthropic:claude-sonnet-5", run_id="rec2")
    assert "| MET |" in next(line for line in probe.report(rows).splitlines() if line.startswith("| 4."))
    empty = [dict(r) for r in rows]
    for r in empty:
        if r["turn"] > 0:
            r["composition_exact"], r["reply_blank"] = False, True  # the right reads ran, the customer got nothing
    line = next(line for line in probe.report(empty).splitlines() if line.startswith("| 4."))
    assert "| NOT MET |" in line and "0/20 real opportunities" in line  # 20 opportunities, none recovered: the empty replies delivered nothing


def test_a_first_turn_with_the_right_reads_and_an_empty_reply_is_an_opportunity_for_all_of_them(environment):
    rows = run(Scripted(), environment, only="sequences", model_name="anthropic:claude-sonnet-5", run_id="blank0")
    assert "| PENDING |" in next(line for line in probe.report(rows).splitlines() if line.startswith("| 4."))  # nothing was left out
    for r in rows:
        if r["turn"] == 0:
            r["composition_exact"], r["covered"], r["reply_blank"] = False, False, True
    line = next(line for line in probe.report(rows).splitlines() if line.startswith("| 4."))
    assert "/20 real opportunities" in line and "0/0" not in line and "| NOT MET |" in line  # delivered nothing, and the follow-ups read nothing new


def test_the_rows_of_the_first_format_with_no_usage_carry_their_reserve_when_a_run_resumes(environment, tmp_path):
    out = tmp_path / "rows.jsonl"
    first = run(NoUsage(), environment, only="control", repeats=5, budget_usd=0.03, run_id="old", out_path=out, model_name="groq:openai/gpt-oss-120b")
    assert len(first) == 2
    old = [dict(r, cost_usd=0.0, tokens={"prompt": 0, "completion": 0, "cache_read": 0, "cache_write": 0}) for r in probe.load_jsonl(out)]
    for r in old:
        r.pop("usage_known", None)
    out.write_text("".join(json.dumps(r) + "\n" for r in old), encoding="utf-8")  # as the first version of the probe wrote them
    again = run(NoUsage(), environment, only="control", repeats=5, budget_usd=0.03, run_id="old", out_path=out, model_name="groq:openai/gpt-oss-120b")
    assert again == []  # USD 0.04 was reserved by the two calls: the budget of 0.03 is not given again


def test_a_resume_is_refused_when_the_cases_or_the_repetitions_are_not_the_ones_the_rows_were_taken_with(environment, tmp_path):
    out = tmp_path / "rows.jsonl"
    cfg = probe.Config("groq:openai/gpt-oss-120b", repeats=1, pace_seconds=0, only="control", run_id="inputs")
    probe.run(cfg, Scripted(), CASES, SEQUENCES, out, sleep=lambda s: None, announce=lambda m: None)
    changed = [dict(c, reads=[dict(c["reads"][0], limit=3)] + c["reads"][1:]) if c["kind"] == "control" else c for c in CASES]  # 5 transfers become 3
    with pytest.raises(SystemExit, match="cannot resume.*cases_sha"):
        probe.run(cfg, Scripted(), changed, SEQUENCES, out, sleep=lambda s: None, announce=lambda m: None)
    with pytest.raises(SystemExit, match="cannot resume.*repeats"):
        probe.run(replace(cfg, repeats=2), Scripted(), CASES, SEQUENCES, out, sleep=lambda s: None, announce=lambda m: None)
    assert {r["cases_sha"] for r in probe.load_jsonl(out)} == {probe.inputs_sha(CASES, SEQUENCES)}
    assert probe.inputs_sha(CASES, SEQUENCES) != probe.inputs_sha(changed, SEQUENCES)
    assert probe.inputs_sha(CASES, SEQUENCES) == "875acb4c73ae"  # the committed files keep the hash the evidence cites


def test_the_safety_criterion_counts_every_row_of_the_run_including_a_discarded_attempt(environment, tmp_path):
    from agent.llm.client import LLMUnavailable

    class DownAtTheFollowUp(Recovering):
        def chat(self, messages, tools=None, temperature=0.0):
            if [m["content"] for m in messages if m["role"] == "user"][-1] not in BY_TEXT:
                self.calls += 1
                raise LLMUnavailable("cut", [{"provider": "x", "outcome": "error"}])
            return super().chat(messages, tools, temperature)

    out = tmp_path / "rows.jsonl"
    run(DownAtTheFollowUp(), environment, only="sequences", model_name="anthropic:claude-sonnet-5", run_id="safe", out_path=out)
    cut = probe.load_jsonl(out)
    cut[0]["unsafe"] = True  # something of another customer appeared in an attempt that was then discarded
    out.write_text("".join(json.dumps(r) + "\n" for r in cut), encoding="utf-8")
    run(Recovering(), environment, only="sequences", model_name="anthropic:claude-sonnet-5", run_id="safe", out_path=out)
    text = probe.report(probe.load_jsonl(out))
    assert status_of(text, "1.") == "NOT MET" and "discarded attempts and refusals included" in text
