"""La compuerta de calidad pasa con la evidencia actual y falla, por separado, con cada empeoramiento."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from eval import gate

REPORTS = Path("eval/reports")


def load(name):
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


@pytest.fixture
def reports():
    return {"offline": load("system_eval.json"), "adversarial": load("system_eval_adversarial.json"),
            "classifier": load("intent_classifier.json")}


def test_the_committed_evidence_meets_the_gate():
    assert gate.check() == []


def proposed(report):
    return gate._proposed(report)


@pytest.mark.parametrize("mutate,expected", [
    (lambda s: s["unsafe_outcomes"].update(k=1), "inseguro"),
    (lambda s: s.update(missed_escalations_n=1), "escalación"),
    (lambda s: s["records_sent_to_model"].update(k=2), "enviados al modelo"),
    (lambda s: s["handoff_completeness"].update(rate=0.99), "traspasos incompletos"),
])
def test_a_safety_regression_fails_in_the_offline_and_in_the_adversarial_run(reports, mutate, expected):
    for label in ("offline", "adversarial"):
        broken = copy.deepcopy(reports[label])
        mutate(proposed(broken))
        assert any(expected in f for f in gate.check_safety(broken, label))


def test_quality_below_the_floor_fails_and_at_the_floor_passes(reports):
    broken = copy.deepcopy(reports["offline"])
    proposed(broken)["safe_automated_resolution"]["rate"] = gate.FLOORS["safe_automated_resolution"] - 0.001
    assert any("safe_automated_resolution" in f for f in gate.check_quality(broken, "offline"))
    proposed(broken)["safe_automated_resolution"]["rate"] = gate.FLOORS["safe_automated_resolution"]
    assert gate.check_quality(broken, "offline") == []


def test_losing_the_fraud_guard_recall_that_we_have_today_fails(reports):
    broken = copy.deepcopy(reports["classifier"])
    broken["test"]["escalation_guard"][gate.GUARD]["recall"].update(k=13, n=15, rate=13 / 15)
    assert any("recall" in f for f in gate.check_guard(broken))
    assert gate.check_guard(reports["classifier"]) == []


def test_evidence_made_with_another_prompt_version_is_stale(reports):
    stale = copy.deepcopy(reports["offline"])
    stale["prompt_version"] = "0.0.1"
    assert any("volver a medir" in f for f in gate.check_fresh({"system_eval.json": stale}))


def test_evidence_measured_with_other_policies_is_stale(reports):
    ok = {**reports["offline"], "policy_sha256": "abc"}
    old = {**reports["offline"], "policy_sha256": "zzz"}
    missing = {k: v for k, v in reports["offline"].items() if k != "policy_sha256"}
    assert gate.check_policy_fresh({"system_eval.json": ok}, current="abc") == []
    assert any("volver a correr" in f for f in gate.check_policy_fresh({"system_eval.json": old}, current="abc"))
    assert any("volver a correr" in f for f in gate.check_policy_fresh({"system_eval.json": missing}, current="abc"))


def test_the_gate_fails_when_the_policies_changed_after_the_reports_were_made(monkeypatch):
    assert gate.check() == []                                          # with the reports just regenerated, it holds
    monkeypatch.setattr(gate, "policy_fingerprint", lambda: "0" * 64)  # ...and the policy files change afterwards
    assert any("volver a correr" in f for f in gate.check())


def test_the_committed_reports_carry_the_current_policy_fingerprint():
    current = gate.policy_fingerprint()
    assert load("system_eval.json")["policy_sha256"] == current == load("system_eval_adversarial.json")["policy_sha256"]


# --- floors per failure category ---------------------------------------------------------------------------------

@pytest.fixture
def failures():
    return load("failure_eval.json")


def test_the_committed_failure_evaluation_meets_its_floors(reports, failures):
    assert gate.check_failure_categories(failures, reports["offline"], reports["adversarial"]) == []


@pytest.mark.parametrize("cell,change,expected", [
    ("unsafe", 1, "inseguro"),
    ("crashed", 1, "caída"),
])
def test_one_unsafe_outcome_or_crash_in_any_category_and_language_fails(reports, failures, cell, change, expected):
    for mode in ("scripted", "adversarial"):
        broken = copy.deepcopy(failures)
        broken["reserved"][mode]["table"]["prompt_injection"]["pt"][cell] = change
        assert any(expected in f and "prompt_injection" in f for f in gate.check_failure_categories(broken, reports["offline"], reports["adversarial"]))


def test_a_category_that_falls_below_its_floor_fails_even_when_the_others_hold(reports, failures):
    from eval.stats import rate

    broken = copy.deepcopy(failures)
    cell = broken["reserved"]["scripted"]["table"]["tool_failure"]["all"]
    cell["handled"] = rate(cell["n"] - 1, cell["n"])
    found = gate.check_failure_categories(broken, reports["offline"], reports["adversarial"])
    assert len(found) == 1 and "tool_failure" in found[0] and "handled" in found[0]


def test_the_generated_workloads_categories_are_held_to_the_same_floors(reports, failures):
    broken = copy.deepcopy(reports["offline"])
    row = next(r for r in broken["cases"]["proposed (scripted)"] if r["template"] == "expired_session")
    row["disposition_ok"] = False
    found = gate.check_failure_categories(failures, broken, reports["adversarial"])
    assert any("workload generado" in f and "expired_session" in f for f in found)


def test_a_failure_report_measured_with_other_policies_is_stale(failures):
    assert gate.check_policy_fresh({"failure_eval.json": failures}) == []
    assert any("volver a correr" in f for f in gate.check_policy_fresh({"failure_eval.json": failures}, current="0" * 64))


# --- the live report ---------------------------------------------------------------------------------------------

LIVE_NAME = "proposed (live: m)"


def _live(fp: str = "f" * 64, runs: int = 2) -> dict:
    """A live report of two cases and `runs` runs, its per-run counts taken from its rows."""
    rows = [{"case_id": c, "repeat": i, "unsafe": [], "records_sent_to_model": [], "safe_resolution": True, "in_scope": True}
            for i in range(1, runs + 1) for c in ("a", "b")]
    repeats = [{"repeat": i, "policy_sha256": fp, "code_sha": "c" * 40, "unsafe_outcomes": {"k": 0},
                "records_sent_to_model": {"k": 0}, "safe_automated_resolution": {"k": 2}} for i in range(1, runs + 1)]
    return {"policy_sha256": fp, "code_sha": "c" * 40, "n_cases": 2, "cases": {LIVE_NAME: rows},
            "systems": {LIVE_NAME: {"repeats": repeats, "repeat_variability": {"runs": runs}}}}


def _docs(*lines: str) -> dict[str, str]:
    return {name: "# doc\n" + "\n".join(lines) for name in gate.LIVE_DOCS}


def test_the_committed_live_report_keeps_every_run_and_says_what_it_measured():
    live = load("system_eval_live.json")
    assert gate.check_live(live) == []
    for name, system in live["systems"].items():
        assert [r["repeat"] for r in system["repeats"]] == list(range(1, system["repeat_variability"]["runs"] + 1))
        assert len(live["cases"][name]) == live["n_cases"] * system["repeat_variability"]["runs"]


def test_a_live_report_with_the_current_fingerprint_needs_no_declaration():
    assert gate.check_live(_live("f" * 64), current="f" * 64, docs=_docs("Live figures below.")) == []


def test_a_live_report_measured_on_other_code_fails_unless_the_docs_say_so():
    live, current = _live("a" * 64), "b" * 64
    silent = gate.check_live(live, current=current, docs=_docs("Live figures below."))
    assert len(silent) == len(gate.LIVE_DOCS) and all("make eval-live" in f for f in silent)
    declared = _docs(f"Live figures {gate.LIVE_STALE}: fingerprint `{'a' * 12}`, the current code is `{'b' * 12}`.")
    assert gate.check_live(live, current=current, docs=declared) == []
    old_declaration = _docs(f"Live figures {gate.LIVE_STALE}: fingerprint `{'a' * 12}`, the current code is `{'9' * 12}`.")
    assert len(gate.check_live(live, current=current, docs=old_declaration)) == len(gate.LIVE_DOCS)


def test_a_declaration_left_behind_after_measuring_again_fails():
    docs = _docs(f"Live figures {gate.LIVE_STALE}: fingerprint `{'a' * 12}`, the current code is `{'f' * 12}`.")
    assert any("borrar la línea" in f for f in gate.check_live(_live("f" * 64), current="f" * 64, docs=docs))


def test_a_live_report_that_dropped_a_runs_rows_or_its_provenance_fails():
    only_run_1 = _live()
    only_run_1["cases"][LIVE_NAME] = [r for r in only_run_1["cases"][LIVE_NAME] if r["repeat"] == 1]
    assert any("corrida 2: 0 filas" in f for f in gate.check_live(only_run_1, current="f" * 64, docs=_docs()))
    no_code = {**_live(), "code_sha": None}
    assert any("code_sha" in f for f in gate.check_live(no_code, current="f" * 64, docs=_docs()))
    fewer_runs = _live()
    fewer_runs["systems"][LIVE_NAME]["repeats"].pop()
    assert any("1 corrida(s) descritas para 2" in f for f in gate.check_live(fewer_runs, current="f" * 64, docs=_docs()))


def test_a_per_run_count_that_does_not_come_from_the_rows_fails():
    live = _live()
    live["cases"][LIVE_NAME][3]["unsafe"] = ["text_outside_the_templates"]  # run 2 had an unsafe outcome...
    found = gate.check_live(live, current="f" * 64, docs=_docs())          # ...that its summary does not publish
    assert any("corrida 2: unsafe_outcomes publica 0, las filas dan 1" in f for f in found)
    other_code = _live()
    other_code["systems"][LIVE_NAME]["repeats"][1]["policy_sha256"] = "e" * 64  # the code changed during the measurement
    assert any("corrida 2: medida con la huella" in f for f in gate.check_live(other_code, current="f" * 64, docs=_docs()))
