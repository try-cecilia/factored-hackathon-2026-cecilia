"""The tracking snapshot: that it reads a real MLflow store, compares each run with its report, and says so when a run disagrees."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from eval import tracking_report as tr

if not Path("eval/reports/system_eval.json").exists():
    pytest.skip("per-case reports are not in the public copy", allow_module_level=True)
CLASSIFIER = json.loads(Path("eval/reports/intent_classifier.json").read_text(encoding="utf-8"))
REPORTS = {mode: json.loads(p.read_text(encoding="utf-8")) for mode, p in tr.SYSTEM_REPORTS.items()}


def classifier_run(**override):
    t, g = CLASSIFIER["test"], CLASSIFIER["test"]["escalation_guard"]["lexicon_or_classifier (runtime)"]
    run = {"experiment": "intent-classifier", "name": "select char+word", "status": "FINISHED", "started": "2026-10-01T05:05:02+00:00",
           "tags": {"git_sha": "abc1234", "git_dirty": "false"}, "artifacts": [],
           "params": {"chosen_variant": CLASSIFIER["chosen_variant"], "escalation_threshold": str(CLASSIFIER["escalation_threshold"]),
                      "train_sha256": CLASSIFIER["versions"]["train_sha256"], "heldout_sha256": CLASSIFIER["versions"]["heldout_sha256"]},
           "metrics": {"test_accuracy": t["learned"]["accuracy"]["rate"], "test_macro_f1": t["learned"]["macro_f1"],
                       "test_baseline_accuracy": t["baseline_keywords"]["accuracy"]["rate"], "test_guard_recall": g["recall"]["rate"]},
           "children": [{"name": f"candidate {v}", "params": {"variant": v}, "metrics": {"dev_macro_f1": s["dev_macro_f1"]}, "tags": {}}
                        for v, s in CLASSIFIER["model_selection_dev"].items()]}
    run["metrics"].update(override.get("metrics", {}))
    run["params"].update(override.get("params", {}))
    return run


def system_run(name: str, mode: str, **metrics):
    s = (REPORTS["scripted"]["systems"] | REPORTS["adversarial"]["systems"])[name]
    values = {"safe_automated_resolution": s["safe_automated_resolution"]["rate"], "unsafe_outcomes": s["unsafe_outcomes"]["rate"],
              "escalation_recall": s["escalation_recall"]["rate"], "missed_escalations_n": s["missed_escalations_n"]} | metrics
    return {"experiment": "system-eval", "name": name, "status": "FINISHED", "started": "2026-10-01T05:06:00+00:00",
            "tags": {"git_sha": "abc1234", "git_dirty": "false"}, "artifacts": [], "children": [], "metrics": values,
            "params": {"llm_mode": mode, "n_cases": "548", "prompt_version": "3.1.0", "prompt_sha256": "0" * 64, "cases_sha256": "1" * 64}}


def test_runs_that_say_what_their_reports_say_are_reported_as_matching():
    runs = [classifier_run(), system_run("proposed (scripted)", "scripted"), system_run("baseline", "none")]
    text = tr.render(runs, CLASSIFIER, REPORTS)
    assert text.count("| all match |") == 3 and "**differs:**" not in text
    assert "`eval/reports/system_eval.json`" in text  # the baseline lives in the offline report, whatever its mode says


def test_a_run_that_disagrees_with_its_report_is_named_not_hidden():
    runs = [classifier_run(metrics={"test_accuracy": 0.5}, params={"chosen_variant": "word"}),
            system_run("proposed (scripted)", "scripted", safe_automated_resolution=0.5)]
    text = tr.render(runs, CLASSIFIER, REPORTS)
    assert "**differs:** chosen representation, test accuracy" in text
    assert "**differs:** safe automated resolution" in text


def test_a_run_no_committed_report_names_is_not_compared_and_says_so():
    odd = system_run("baseline", "none")
    odd["name"] = "proposed (live: some-model)"
    odd["metrics"] = {"safe_automated_resolution": 0.9}
    text = tr.render([odd], CLASSIFIER, REPORTS)
    assert "no committed report names this run" in text and "not compared" in text


def test_the_snapshot_states_what_it_leaves_out_and_the_code_it_was_made_with():
    text = tr.render([classifier_run(), system_run("baseline", "none")], CLASSIFIER, REPORTS)
    assert "live-model runs" in text and "`abc1234`" in text and "uncommitted changes: `false`" in text
    assert "a snapshot, not a live view" in text.lower()


def test_a_run_that_did_not_finish_is_listed():
    bad = classifier_run()
    bad["status"] = "FAILED"
    assert "`FAILED`" in tr.render([bad], CLASSIFIER, REPORTS)


def test_it_reads_a_real_store_with_nested_runs(tmp_path, monkeypatch):
    pytest.importorskip("mlflow")
    from eval import tracking

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:///" + (tmp_path / "m.db").as_posix())
    with tracking.run("intent-classifier", "select char+word", tags={"report_generated_at": "x"}) as mlflow:
        assert mlflow is not None
        mlflow.log_params({"chosen_variant": "char+word", "escalation_threshold": 0.55})
        mlflow.log_metric("test_accuracy", 0.847)
        for variant, score in (("char", 0.8), ("word", 0.7)):
            with mlflow.start_run(run_name=f"candidate {variant}", nested=True):
                mlflow.log_param("variant", variant)
                mlflow.log_metric("dev_macro_f1", score)
    runs = tr.load_runs("sqlite:///" + (tmp_path / "m.db").as_posix())
    assert [r["name"] for r in runs] == ["select char+word"]  # the candidates are children, not top-level runs
    assert {c["params"]["variant"] for c in runs[0]["children"]} == {"char", "word"}
    assert runs[0]["metrics"]["test_accuracy"] == 0.847 and runs[0]["status"] == "FINISHED" and "git_sha" in runs[0]["tags"]
