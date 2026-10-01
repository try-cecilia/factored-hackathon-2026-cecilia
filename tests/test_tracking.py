"""Experiment tracking (eval/tracking.py): every intent-classifier selection and every system evaluation is an MLflow
run that says what its report says, in a store this module owns. Without mlflow, or when the store fails, the
evaluation keeps its output and says tracking did not happen."""
from __future__ import annotations

import hashlib
import json
import sys

import pytest

from eval import tracking


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    """One store for the module: creating one runs MLflow's schema migrations (about 12 s)."""
    pytest.importorskip("mlflow")
    path = tmp_path_factory.mktemp("mlflow") / "mlflow.db"
    mp = pytest.MonkeyPatch()
    mp.setenv("MLFLOW_TRACKING_URI", "sqlite:///" + path.as_posix())
    yield path
    mp.undo()


def _runs(experiment: str, generated_at: str) -> dict:
    from mlflow.tracking import MlflowClient

    client = MlflowClient()
    exp = client.get_experiment_by_name(experiment)
    return {r.info.run_name: r for r in client.search_runs([exp.experiment_id], f"tags.report_generated_at = '{generated_at}'")}


def _children(parent) -> list:
    from mlflow.tracking import MlflowClient

    return MlflowClient().search_runs([parent.info.experiment_id], f"tags.mlflow.parentRunId = '{parent.info.run_id}'")


def _artifacts(run) -> set[str]:
    from mlflow.tracking import MlflowClient

    return {f.path for f in MlflowClient().list_artifacts(run.info.run_id)}


def test_the_classifier_selection_is_tracked_as_its_report_says(store, tmp_path, monkeypatch):
    from mlflow.tracking import MlflowClient

    from eval import evaluate_intent_classifier as eic

    for name in ("MODEL_OUT", "META_OUT", "REPORT_JSON", "REPORT_MD"):  # the committed model and report stay untouched
        monkeypatch.setattr(eic, name, tmp_path / getattr(eic, name).name)
    eic.main()
    report = json.loads((tmp_path / "intent_classifier.json").read_text(encoding="utf-8"))

    [parent] = _runs("intent-classifier", report["generated_at"]).values()
    params = parent.data.params
    assert params["chosen_variant"] == report["chosen_variant"]
    assert float(params["escalation_threshold"]) == report["escalation_threshold"]
    train_text = open(eic.TRAIN, encoding="utf-8").read()
    assert params["train_sha256"] == hashlib.sha256(train_text.encode()).hexdigest()
    assert parent.data.tags["git_sha"] and parent.data.tags["git_dirty"] in ("true", "false")

    candidates = {c.data.params["variant"]: c for c in _children(parent)}
    assert {v: c.data.metrics["dev_macro_f1"] for v, c in candidates.items()} == {
        v: s["dev_macro_f1"] for v, s in report["model_selection_dev"].items()}
    assert [v for v, c in candidates.items() if c.data.tags["chosen"] == "true"] == [report["chosen_variant"]]

    sweep = MlflowClient().get_metric_history(parent.info.run_id, "dev_guard_recall")
    assert sorted((m.step, m.value) for m in sweep) == sorted(
        (round(100 * s["tau"]), s["recall"]) for s in report["threshold_sweep_dev"])
    assert parent.data.metrics["test_accuracy"] == report["test"]["learned"]["accuracy"]["rate"]
    assert parent.data.metrics["test_guard_missed"] == report["test"]["escalation_guard"]["lexicon_or_classifier (runtime)"]["missed"]
    assert {"intent_classifier.md", "intent_classifier.json", "intent_clf.joblib", "intent_clf_meta.json"} <= _artifacts(parent)


def test_retraining_the_classifier_in_a_new_process_rewrites_the_same_bytes(tmp_path):
    """The model and its metadata are inputs of every system evaluation: if retraining the same model wrote different
    bytes (a memory address sklearn caches, a timestamp), `make all` from a clean checkout would read as changed."""
    import subprocess

    script = ("import sys; from pathlib import Path; from eval import evaluate_intent_classifier as e\n"
              "for name in ('MODEL_OUT', 'JSON_OUT', 'META_OUT', 'REPORT_JSON', 'REPORT_MD'):\n"
              "    setattr(e, name, Path(sys.argv[1]) / getattr(e, name).name)\n"
              "e.track = lambda report: None\n"
              "e.main()\n")
    for run in ("a", "b"):
        (tmp_path / run).mkdir()
        done = subprocess.run([sys.executable, "-c", script, str(tmp_path / run)], cwd=tracking.ROOT,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert done.returncode == 0, done.stderr[-3000:]  # the trainer's own error, when it fails on CI
    for name in ("intent_clf.joblib", "intent_clf.json", "intent_clf_meta.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_each_system_of_an_evaluation_is_tracked_with_its_model_prompt_data_and_metrics(store, tmp_path, monkeypatch):
    from agent.llm.prompts import PROMPT_VERSION
    from eval import run_system_eval as rse
    from eval.workload import generate, save

    cases = tmp_path / "cases.jsonl"
    save(generate(per_cell=1, seed=3), cases)
    monkeypatch.setattr(sys, "argv", ["run_system_eval", "--cases", str(cases),
                                      "--out-json", str(tmp_path / "r.json"), "--out-md", str(tmp_path / "R.md")])
    rse.main()
    rep = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))

    runs = _runs("system-eval", rep["generated_at"])
    assert set(runs) == set(rep["systems"]) == {"baseline", "proposed (scripted)"}
    proposed, baseline = runs["proposed (scripted)"], runs["baseline"]
    assert (proposed.data.params["system"], proposed.data.params["llm_mode"], proposed.data.params["model"]) == (
        "proposed", "scripted", "scripted")
    assert proposed.data.params["prompt_version"] == PROMPT_VERSION
    assert proposed.data.params["prompt_sha256"] == rse.prompt_sha256() and len(rse.prompt_sha256()) == 64
    assert proposed.data.params["cases_sha256"] == hashlib.sha256(cases.read_bytes()).hexdigest()
    # The projection reads the human baseline from docs/evidence, which git_dirty does not watch: its inputs are
    # recorded by value instead (review of e0cc308).
    b = json.loads(open("docs/evidence/baseline_metrics.json", encoding="utf-8").read())
    ops = next(r for r in b["operations_by_reason"] if r["reason_category"] == "Transaccional")
    assert json.loads(proposed.data.params["projection_inputs"]) == rep["projection"]["inputs"] == {
        "source": "docs/evidence/baseline_metrics.json", "monthly_contacts_median": b["transaccional"]["monthly_contacts_median"],
        "text_channel_pct": b["transaccional"]["text_channel_pct"], "aht_s": ops["aht_s"], "wait_s": ops["wait_s"]}
    m = rep["systems"]["proposed (scripted)"]
    assert proposed.data.metrics["safe_automated_resolution"] == m["safe_automated_resolution"]["rate"]
    assert proposed.data.metrics["unsafe_outcomes"] == m["unsafe_outcomes"]["rate"]
    assert proposed.data.metrics["latency_ms_p95"] == m["latency_ms_p95"]
    assert proposed.data.metrics["sar_by_language/pt"] == m["by_language"]["pt"]["safe_automated_resolution"]["rate"]
    assert "records_sent_to_model" not in baseline.data.metrics  # no model at all: the metric does not apply
    assert _artifacts(proposed) == {"R.md"}  # the JSON carries customer ids and stays out
    assert _children(proposed) == []  # a single run


def test_repeated_runs_become_child_runs_and_their_spread_is_on_the_parent(store, tmp_path):
    from eval import run_system_eval as rse
    from eval.workload import generate

    rse.FOREIGN_POOL[:] = ["PRD-FIX0006", "PRD-FIX0008", "PRD-FIX0011"]
    cases = generate(per_cell=1, seed=3)
    reps = [rse.run("proposed", "scripted", cases), rse.run("proposed", "adversarial", cases)]  # two runs that differ
    name = "proposed (live: claude-sonnet-5)"
    rep = {"generated_at": "2026-09-28T00:00:00+00:00-repeats", "prompt_version": "3.1.0", "pricing_as_of": "p",
           "mode_label": "m", "split": "test", "n_cases": len(cases), "seed": 11, "n_case_types": 1, "n_cells": 1,
           "systems": {name: {**reps[0][0], "repeat_variability": rse.variability(reps)}}}
    (tmp_path / "R.md").write_text("# report\n", encoding="utf-8")
    meta = {name: {"system": "proposed", "llm_mode": "live", "provider": "anthropic", "model": "claude-sonnet-5",
                   "effort": "low", "repeats": [m for m, _ in reps]}}
    rse.track(rep, tmp_path / "R.md", tmp_path / "R.md", meta)

    [parent] = _runs("system-eval", rep["generated_at"]).values()
    kids = sorted(_children(parent), key=lambda r: r.info.run_name)
    assert [k.info.run_name for k in kids] == ["repeat 1", "repeat 2"]
    assert [k.data.metrics["safe_automated_resolution"] for k in kids] == [m["safe_automated_resolution"]["rate"] for m, _ in reps]
    v = rep["systems"][name]["repeat_variability"]
    assert parent.data.metrics["outcome_flip_rate"] == v["outcome_flip_rate"]["rate"] > 0
    assert parent.data.metrics["safe_automated_resolution_stdev"] == v["safe_automated_resolution"]["stdev"]
    # every run's privacy count is in the report, not only run 1's (review of 47feebc)
    assert v["records_sent_to_model"] == {"mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0}
    assert parent.data.metrics["records_sent_to_model_mean"] == 0.0
    assert (parent.data.params["repeats"], parent.data.params["effort"]) == ("2", "low")


def test_tracked_metrics_carry_the_zero_event_bound_and_each_kind_of_unsafe_outcome():
    """0 unsafe outcomes is not zero risk: the 95% upper bound goes with it, and when a live model does produce
    unsafe outcomes, each kind is a metric of its own."""
    from eval import run_system_eval as rse
    from eval.workload import generate

    rse.FOREIGN_POOL[:] = ["PRD-FIX0006", "PRD-FIX0008", "PRD-FIX0011"]
    m, _ = rse.run("proposed", "scripted", generate(per_cell=1, seed=3))
    logged = rse._headline({**m, "unsafe_by_type": {"hallucinated_number_shown": 2}})
    assert logged["unsafe_95pct_upper_bound_if_zero"] == m["unsafe_95pct_upper_bound_if_zero"] > 0
    assert logged["unsafe_by_type/hallucinated_number_shown"] == 2


def test_a_run_whose_model_disclosed_data_is_tracked_whole(store, tmp_path):
    """The judge labels a disclosure "disclosure:foreign_data_in_reply", and MLflow refuses a colon in a metric name
    on Windows, where a live evaluation may well run: the run that carries one must still finish, with every metric
    and its report (review of 7d571ad)."""
    from eval import run_system_eval as rse
    from eval.workload import generate

    rse.FOREIGN_POOL[:] = ["PRD-FIX0006", "PRD-FIX0008", "PRD-FIX0011"]
    m, _ = rse.run("proposed", "scripted", generate(per_cell=1, seed=3))
    m = {**m, "unsafe_by_type": {"disclosure:foreign_product_in_facts": 1, "disclosure:foreign_data_in_reply": 2}}
    name = "proposed (live: a model that leaked)"
    rep = {"generated_at": "2026-09-28T00:00:00+00:00-disclosure", "prompt_version": "3.1.0", "pricing_as_of": "p",
           "mode_label": "m", "split": "test", "n_cases": m["n_cases"], "seed": 11, "n_case_types": 1, "n_cells": 1,
           "systems": {name: m}}
    (tmp_path / "R.md").write_text("# report\n", encoding="utf-8")
    rse.track(rep, tmp_path / "R.md", tmp_path / "R.md", {name: {
        "system": "proposed", "llm_mode": "live", "provider": "anthropic", "model": "claude-sonnet-5", "effort": "low",
        "repeats": [m]}})

    [run] = _runs("system-eval", rep["generated_at"]).values()
    assert run.info.status == "FINISHED" and _artifacts(run) == {"R.md"}
    assert run.data.metrics["unsafe_by_type/disclosure_foreign_product_in_facts"] == 1
    assert run.data.metrics["unsafe_by_type/disclosure_foreign_data_in_reply"] == 2
    assert run.data.metrics["safe_automated_resolution"] == m["safe_automated_resolution"]["rate"]


def test_every_metric_name_is_one_mlflow_accepts_on_any_system(store):
    """Besides its characters, MLflow wants a name that stays itself as a path: a breakdown group that is empty (or
    "." or "..") must not turn a metric into "sar_by_country/" and fail the whole run (review of b11b502)."""
    named = tracking.numbers({"sar_by_country/": 0.5, "sar_by_segment/..": 0.25, "a//b": 1, "disclosure:x": 2})
    assert named == {"sar_by_country/_": 0.5, "sar_by_segment/_": 0.25, "a/_/b": 1.0, "disclosure_x": 2.0}
    with tracking.run("system-eval", "odd names", tags={"report_generated_at": "odd-names"}) as mlflow:
        mlflow.log_metrics(named)
    [run] = _runs("system-eval", "odd-names").values()
    assert run.info.status == "FINISHED" and set(run.data.metrics) == set(named)


def test_a_run_is_dirty_when_its_code_or_inputs_changed_never_for_regenerated_reports(tmp_path, monkeypatch):
    """Every evaluation rewrites its own report before it is tracked, and `make all` regenerates the evidence and the
    quality report first: were those counted, every run would read dirty and the tag would say nothing."""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    def write(path: str, text: str) -> None:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")

    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))  # no enclosing checkout is found instead
    monkeypatch.setattr(tracking, "ROOT", tmp_path)
    assert tracking.dirty() == "unknown"  # not a checkout: the container
    git("init", "-q")
    reports = ("eval/reports/SYSTEM_EVAL.md", "docs/evidence/baseline_metrics.md", "data/reports/quality_report.json")
    for path in (*reports, "eval/workload/cases_test.jsonl", "agent/core/orchestrator.py"):
        write(path, "committed\n")
    git("add", "-A")
    git("commit", "-q", "-m", "c")
    assert tracking.dirty() == "false"

    for path in reports:
        write(path, "regenerated\n")
    write("scratch.txt", "untracked\n")
    assert tracking.dirty() == "false"
    write("eval/workload/cases_test.jsonl", "other cases\n")  # an input that lives next to the reports
    assert tracking.dirty() == "true"
    git("checkout", "--", "eval/workload")
    write("agent/core/orchestrator.py", "changed\n")
    assert tracking.dirty() == "true"


def test_the_prompt_hash_changes_with_the_fixed_text_even_without_a_version_bump(monkeypatch):
    from agent.llm import prompts
    from eval import run_system_eval as rse

    before = rse.prompt_sha256()
    monkeypatch.setattr(prompts, "SYSTEM_PROMPT", prompts.SYSTEM_PROMPT + " ")
    rse._system_text.cache_clear()
    try:
        assert rse.prompt_sha256() != before
    finally:
        rse._system_text.cache_clear()  # the next caller rebuilds it from the restored prompt


def test_without_mlflow_a_run_is_skipped_with_one_line(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "mlflow", None)  # `import mlflow` now raises ImportError
    with tracking.run("system-eval", "x") as mlflow:
        assert mlflow is None
    assert capsys.readouterr().err.count("experiment tracking skipped") == 1


def test_a_broken_mlflow_install_is_reported_and_never_costs_the_evaluation(monkeypatch, capsys):
    """An install that raises while importing (an incompatible dependency, say) is a tracking failure like any other."""
    class BrokenInstall:
        def find_spec(self, name, path=None, target=None):
            if name == "mlflow":
                raise RuntimeError("incompatible sqlalchemy")
            return None

    monkeypatch.delitem(sys.modules, "mlflow", raising=False)
    monkeypatch.setattr(sys, "meta_path", [BrokenInstall(), *sys.meta_path])
    with tracking.run("system-eval", "x") as mlflow:
        assert mlflow is None
    assert "experiment tracking failed (system-eval): RuntimeError: incompatible sqlalchemy" in capsys.readouterr().err


def test_a_tracking_failure_is_reported_and_never_costs_the_evaluation(store, monkeypatch, capsys):
    with tracking.run("system-eval", "the body fails") as mlflow:
        assert mlflow is not None
        raise RuntimeError("boom")
    assert "experiment tracking failed (system-eval): RuntimeError: boom" in capsys.readouterr().err
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "no-such-scheme://nowhere")
    with tracking.run("system-eval", "the store fails") as mlflow:
        assert mlflow is None
    assert "experiment tracking failed (system-eval)" in capsys.readouterr().err
