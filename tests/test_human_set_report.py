"""The report of the human set: the pre-registered gates G0 to G4 computed from the standard evaluation report.

No model runs here. The "live" reports are built from synthetic per-case rows with the evaluation's own metric code
(run_system_eval.metrics, breakdown, variability), so they have exactly the shape a live run writes. Every message is
**fake data written to test the report**.
"""
from __future__ import annotations

import json
import sys

import pytest

from eval import run_system_eval as rse
from eval.human_set import report as hr

ALL = ["AUTO_RESOLVE", "CLARIFY", "ABSTAIN", "ESCALATE"]
TYPES = [("balance_all", ["AUTO_RESOLVE"]), ("balance_specific", ["AUTO_RESOLVE"]), ("transactions", ["AUTO_RESOLVE"]),
         ("payment_ok", ["AUTO_RESOLVE"]), ("fx", ["AUTO_RESOLVE"]), ("trace_confirm", ["AUTO_RESOLVE"]), ("fraud", ["ESCALATE"]),
         ("out_of_scope", ["ABSTAIN"]), ("ambiguous_type", ["CLARIFY"]), ("family_account", ALL)]


def row(i: int, actual: str | None = None, unsafe=(), accept=None) -> dict:
    """One judged case, with the fields the metrics read: case type i % 10, the expected outcome unless told otherwise."""
    template, expected = TYPES[i % 10]
    accept = accept or expected
    actual = actual or accept[0]
    escalated = actual == "ESCALATE"
    return {"case_id": f"c{i:03d}", "template": template, "category": "x", "language": "pt" if i % 3 == 0 else "es",
            "segment": "Basic", "country": "México", "expected": accept, "actual": actual, "actual_category": None,
            "disposition_ok": actual in accept, "in_scope": accept == ["AUTO_RESOLVE"],
            "resolution_correct": actual in accept if actual == "AUTO_RESOLVE" else None, "resolution_required": True,
            "safe_resolution": actual == "AUTO_RESOLVE" and actual in accept and not unsafe, "unsafe": list(unsafe),
            "incorrect_not_unsafe": [], "transfer_attempted": escalated, "escalated": escalated,
            "should_escalate": accept == ["ESCALATE"], "escalation_acceptable": "ESCALATE" in accept,
            "ticket_complete": True if escalated else None, "records_sent_to_model": [],
            "disposition_scored": not set(ALL) <= set(accept), "latency_ms": 1500.0 + i, "cost_usd": 0.001, "tokens": 400,
            "llm_calls": 1, "model": "anthropic/claude-sonnet-5", "rule": "llm", "model_chose": [], "turns": [f"mensaje {i}"]}


def system(rows: list[dict]) -> dict:
    m = rse.metrics(rows)
    for key in ("template", "category", "language", "segment", "country"):
        m[f"by_{key}"] = rse.breakdown(rows, key)
    m["served_by"] = {"anthropic/claude-sonnet-5": len(rows)}
    m["error_analysis"] = rse.error_analysis(rows)
    return m


def live_report(bot_rows: list[dict], runs: list[list[dict]], mode: str = "live") -> dict:
    model = system(runs[0])
    if len(runs) > 1:
        model["repeat_variability"] = rse.variability([(system(r), r) for r in runs])
    name = f"proposed ({mode})"
    return {"generated_at": "2026-10-01T20:00:00+00:00", "prompt_version": "3.1.0", "policy_sha256": "ab" * 32, "pricing_as_of": "x",
            "mode_label": "LIVE LLM", "split": "external", "n_cases": len(bot_rows), "seed": None, "cases_file": "human_cases.jsonl",
            "systems": {"baseline": system(bot_rows), name: model}, "llm_mode": mode, "cases": {"baseline": bot_rows, name: runs[0]}}


def meta_for(n: int, people: int = 9) -> dict:
    return {"generated_at": "2026-10-01T18:00:00+00:00", "warehouse_as_of": "2026-06-17", "cases": n, "people": people,
            "messages_written": n + 6, "people_who_wrote": people, "left_out_saw_system": 1,
            "people_by_country": {"AR": people - 3, "BR": 2, "MX": 1}, "people_by_language": {"es": people - 2, "pt": 2},
            "cases_by_language": {"es": n - n // 3, "pt": n // 3}, "cases_by_situation": {}, "by_final_label": {"matches": n - 4, "ambiguous": 4},
            "dropped": {"something_else": 3, "unresolved": 2, "unlabeled": 1},
            "placeholder_1234": {"replaced": 12, "absent": {"balance_specific": 1, "transactions": 0}}, "near_identical_to_training": 2,
            "case_ids": {f"m{i}": f"c{i:03d}" for i in range(n)}, "labels": {f"m{i}": "matches" for i in range(n)}}


AGREEMENT = {"n": 70, "kappa": 0.72, "percent_agreement": 0.86, "resolved_by_third": 8, "unresolved": 2,
             "confusion": {f"{a}|{b}": 1 for a in ("matches", "ambiguous", "something_else") for b in ("matches", "ambiguous", "something_else")},
             "disagreements": [{"message_id": "m1", "message": "un desacuerdo", "a": "matches", "b": "ambiguous", "third": "matches"}],
             "note": "kappa is computed on the first two people before any disagreement is settled"}
TEXTS = {f"m{i}": f"mensaje escrito {i}, con 1234" for i in range(80)}


def clean(n: int = 64) -> list[dict]:
    return [row(i) for i in range(n)]


def weak_bot(n: int = 64) -> list[dict]:
    """The keyword bot: asks back on half of what it could answer and misses one fraud report in three."""
    return [row(i, "CLARIFY") if (TYPES[i % 10][1] == ["AUTO_RESOLVE"] and i % 2) or (TYPES[i % 10][0] == "fraud" and i % 3 == 0)
            else row(i) for i in range(n)]


def build(runs, bot=None, n=64, agreement=AGREEMENT, people=9, mode="live"):
    return hr.build(agreement, meta_for(n, people), live_report(bot or weak_bot(n), runs, mode), TEXTS)


def test_a_clean_set_meets_every_gate_and_says_how_each_was_computed():
    rep = build([clean(), clean(), clean()])
    assert rep["is_result"] and rep["verdict"] == "reported"
    assert [rep["gates"][g]["passed"] for g in ("G0", "G1", "G2", "G3", "G4")] == [True] * 5
    assert rep["gates"]["G3"]["wording"].startswith("above the keyword bot's")
    md = hr.to_markdown(rep)
    assert "NOT A RESULT" not in md and "Cohen's kappa" in md and "lowest of the three live runs" in md
    assert "not changed on these messages" in md and "docs/preregistration.md" in md
    assert "AR 6" in md and "pt 2" in md  # who wrote it, by country and language


def test_below_the_floor_the_report_is_not_a_result_and_says_so_at_the_top():
    for rep in (build([clean(40)] * 3, bot=weak_bot(40), n=40), build([clean()] * 3, people=7),
                build([clean()] * 3, agreement={**AGREEMENT, "kappa": 0.55}), build([clean()] * 3, agreement={**AGREEMENT, "kappa": None})):
        assert not rep["is_result"] and not rep["gates"]["G0"]["passed"] and rep["verdict"].startswith("NOT A RESULT")
        md = hr.to_markdown(rep)
        assert md.startswith("# The human-written set: NOT A RESULT") and "must not be quoted" in md.split("\n## ")[0]


def test_one_unsafe_outcome_in_any_live_run_fails_g1_even_if_run_1_is_clean():
    run2 = clean()
    run2[5] = row(5, unsafe=["wrong_account_or_figure"])
    rep = build([clean(), run2, clean()])
    assert not rep["gates"]["G1"]["passed"] and rep["gates"]["G2"]["passed"]
    missed = clean()
    missed[6] = row(6, "CLARIFY")  # a fraud report the model asked about instead of handing over
    assert not build([clean(), clean(), missed])["gates"]["G1"]["passed"]


def test_g1_and_g2_need_the_three_live_runs():
    rep = build([clean()])
    assert not rep["gates"]["G1"]["passed"] and not rep["gates"]["G2"]["passed"] and "3 live runs" in rep["gates"]["G1"]["note"]


def test_g2_compares_fraud_recall_with_the_bot_and_caps_false_escalations_in_every_run():
    same = clean()
    same[6], same[16] = row(6, "CLARIFY"), row(16, "CLARIFY")  # 4 of the 6 fraud reports handed over: the bot's 4 of 6
    assert build([clean(), same, clean()])["gates"]["G2"]["passed"]
    worse = clean()
    worse[6], worse[16], worse[26] = row(6, "CLARIFY"), row(16, "CLARIFY"), row(26, "CLARIFY")  # 3 of 6: under the bot's
    assert not build([clean(), worse, clean()])["gates"]["G2"]["passed"]
    handed = clean()
    for i in (0, 1, 2):  # 3 of the 52 cases where a handoff is not acceptable: 5.8%
        handed[i] = row(i, "ESCALATE")
    rep = build([clean(), clean(), handed])
    assert not rep["gates"]["G2"]["passed"] and rep["gates"]["G2"]["false_escalations_highest_run"] > 0.05


def test_g2_refuses_to_call_a_recall_the_fraud_recall_when_other_cases_require_an_escalation():
    odd = clean()
    odd[0] = row(0, "ESCALATE", accept=["ESCALATE"])  # a balance case that would require a handoff
    with pytest.raises(ValueError, match="fraud"):
        build([odd, odd, odd])


def test_overlapping_intervals_are_no_detectable_difference_never_better():
    bot = [row(i) if TYPES[i % 10][1] != ["AUTO_RESOLVE"] or i % 7 else row(i, "CLARIFY") for i in range(64)]
    rep = build([clean()] * 3, bot=bot)
    assert not rep["gates"]["G3"]["passed"]
    assert rep["gates"]["G3"]["wording"] == "no detectable difference at this sample size"
    assert "better" not in hr.to_markdown(rep).split("## ")[1].lower()  # the gates section


def test_a_drop_over_ten_points_in_any_run_must_be_stated_in_the_summary_of_evaluation():
    low = [row(i, "CLARIFY") if TYPES[i % 10][1] == ["AUTO_RESOLVE"] and i % 4 == 0 else row(i) for i in range(64)]  # 30 of 40
    later = build([clean(), low, clean()])["gates"]["G4"]
    assert not later["passed"] and (later["drop_points"], later["drop_points_run1"]) == (20.0, -5.0)
    rep = build([low, clean(), clean()])
    assert rep["gates"]["G4"]["failing_types_run1"] == {"balance_all": 4, "fx": 3, "transactions": 3}
    md = hr.to_markdown(rep)
    assert "summary of `EVALUATION.md`" in md and "balance_all (4)" in md
    assert "summary of `EVALUATION.md`" not in hr.to_markdown(build([clean()] * 3))


def test_failing_messages_are_quoted_as_written_and_nothing_carries_a_dataset_id():
    run1 = clean()
    run1[4] = row(4, "CLARIFY")
    run1[4]["records_sent_to_model"] = ["PRD-00AB12CD"]  # what a row may carry: it must not reach the report
    rep = build([run1, clean(), clean()])
    assert [e["message"] for e in rep["examples"]] == ["mensaje escrito 4, con 1234"]  # the original, with its 1234
    text = json.dumps(rep, ensure_ascii=False) + hr.to_markdown(rep)
    assert "PRD-" not in text and "CLI-" not in text
    with pytest.raises(ValueError, match="dataset id"):
        hr.build(AGREEMENT, meta_for(64), live_report(weak_bot(), [run1, clean(), clean()]), {**TEXTS, "m4": "mi cuenta PRD-00AB12CD"})


def test_it_refuses_an_offline_run_a_run_on_other_cases_and_two_models_at_once():
    with pytest.raises(SystemExit, match="live"):
        build([clean()] * 3, mode="scripted")
    with pytest.raises(SystemExit, match="other cases"):
        hr.build(AGREEMENT, meta_for(65), live_report(weak_bot(), [clean()] * 3), TEXTS)
    two = live_report(weak_bot(), [clean()] * 3)
    two["systems"]["proposed (live: other)"] = two["systems"]["proposed (live)"]
    with pytest.raises(SystemExit, match="one live model"):
        hr.build(AGREEMENT, meta_for(64), two, TEXTS)
    keyless = live_report(weak_bot(), [clean()] * 3)  # no key: every turn fell back without a model
    keyless["systems"]["proposed (live)"]["served_by"] = {}
    with pytest.raises(SystemExit, match="reached a model"):
        hr.build(AGREEMENT, meta_for(64), keyless, TEXTS)


def test_the_command_writes_the_report_and_its_json(tmp_path, monkeypatch):
    paths = {"AGREEMENT": AGREEMENT, "META": meta_for(64), "LIVE": live_report(weak_bot(), [clean()] * 3)}
    for name, data in paths.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(hr, name, tmp_path / f"{name}.json")
    raw = tmp_path / "raw.jsonl"
    raw.write_text(json.dumps({"id": 1, "created_at": "x", "lang": "es", "country": "AR", "saw_system": 0, "consent_version": "x",
                               "answers": {"fx": "a cuanto esta"}}) + "\n", encoding="utf-8")
    monkeypatch.setattr(hr, "RAW", raw)
    monkeypatch.setattr(hr, "OUT_MD", tmp_path / "HUMAN_SET.md")
    monkeypatch.setattr(hr, "OUT_JSON", tmp_path / "human_set.json")
    monkeypatch.setattr(sys, "argv", ["report"])
    hr.main()
    assert json.loads((tmp_path / "human_set.json").read_text(encoding="utf-8"))["is_result"]
    assert (tmp_path / "HUMAN_SET.md").read_text(encoding="utf-8").startswith("# The human-written set: reported")
