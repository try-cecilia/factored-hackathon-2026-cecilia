"""A versioned snapshot of the MLflow runs: what was tracked, on which code and data, and whether each run says what the committed report says.

    python -m eval.tracking_report                       # reads mlruns/mlflow.db, writes docs/evidence/ml_tracking.md
    python -m eval.tracking_report --store sqlite:///x.db --out somewhere.md

The MLflow store is local and git-ignored (`eval/tracking.py`), so a reader of the repository sees none of it. This turns
the top-level runs of `intent-classifier` and `system-eval` into a table that can be read, and checks every run's headline
numbers against the committed reports (`eval/reports/*.json`): a run that disagrees with its report is printed as such, not hidden.

`render` is a pure function of the runs and the reports, so it is tested without a store; `load_runs` is the only part that
needs MLflow.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("docs/evidence/ml_tracking.md")
CLASSIFIER_REPORT = Path("eval/reports/intent_classifier.json")
SYSTEM_REPORTS = {"scripted": Path("eval/reports/system_eval.json"), "adversarial": Path("eval/reports/system_eval_adversarial.json")}
TOLERANCE = 1e-4  # reports round rates to four decimals


def load_runs(store_uri: str) -> list[dict]:
    """The top-level runs of every experiment, oldest first, each with its child runs and artifact names."""
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(store_uri)
    client = MlflowClient()
    runs = []
    for exp in client.search_experiments():
        found = client.search_runs([exp.experiment_id], max_results=1000)
        children: dict[str, list] = {}
        for r in found:
            parent = r.data.tags.get("mlflow.parentRunId")
            if parent:
                children.setdefault(parent, []).append(r)
        for r in found:
            if r.data.tags.get("mlflow.parentRunId"):
                continue
            runs.append({
                "experiment": exp.name, "name": r.info.run_name, "status": r.info.status,
                "started": datetime.fromtimestamp(r.info.start_time / 1000, timezone.utc).isoformat(timespec="seconds"),
                "tags": dict(r.data.tags), "params": dict(r.data.params), "metrics": dict(r.data.metrics),
                "artifacts": sorted(a.path for a in client.list_artifacts(r.info.run_id)),
                "children": [{"name": c.info.run_name, "params": dict(c.data.params), "metrics": dict(c.data.metrics), "tags": dict(c.data.tags)}
                             for c in sorted(children.get(r.info.run_id, []), key=lambda c: c.info.run_name)]})
    return sorted(runs, key=lambda r: r["started"])


def _close(a, b) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= TOLERANCE


def classifier_checks(run: dict, report: dict) -> list[tuple[str, bool]]:
    m, t = run["metrics"], report["test"]
    guard = t["escalation_guard"]["lexicon_or_classifier (runtime)"]
    candidates = {c["params"].get("variant"): c["metrics"].get("dev_macro_f1") for c in run["children"]}
    return [
        ("chosen representation", run["params"].get("chosen_variant") == report["chosen_variant"]),
        ("escalation threshold", _close(run["params"].get("escalation_threshold"), report["escalation_threshold"])),
        ("test accuracy", _close(m.get("test_accuracy"), t["learned"]["accuracy"]["rate"])),
        ("test macro-F1", _close(m.get("test_macro_f1"), t["learned"]["macro_f1"])),
        ("baseline test accuracy", _close(m.get("test_baseline_accuracy"), t["baseline_keywords"]["accuracy"]["rate"])),
        ("runtime guard recall", _close(m.get("test_guard_recall"), guard["recall"]["rate"])),
        ("candidates' dev macro-F1", all(_close(candidates.get(v), s["dev_macro_f1"]) for v, s in report["model_selection_dev"].items())),
        ("training and held-out data hashes", run["params"].get("train_sha256") == report["versions"]["train_sha256"]
         and run["params"].get("heldout_sha256") == report["versions"]["heldout_sha256"]),
    ]


def report_for(run: dict, reports: dict[str, dict]) -> tuple[Path, dict] | None:
    """The committed report that holds this system: the one that names it, offline first (the keyword baseline is only in that one)."""
    for mode in SYSTEM_REPORTS:
        if mode in reports and run["name"] in reports[mode]["systems"]:
            return SYSTEM_REPORTS[mode], reports[mode]
    return None


def system_checks(run: dict, report: dict | None) -> list[tuple[str, bool]]:
    if report is None or run["name"] not in report["systems"]:
        return []
    s, m = report["systems"][run["name"]], run["metrics"]
    return [("safe automated resolution", _close(m.get("safe_automated_resolution"), s["safe_automated_resolution"]["rate"])),
            ("unsafe outcomes", _close(m.get("unsafe_outcomes"), s["unsafe_outcomes"]["rate"])),
            ("escalation recall", _close(m.get("escalation_recall"), s["escalation_recall"]["rate"])),
            ("missed escalations", _close(m.get("missed_escalations_n"), s["missed_escalations_n"]))]


def _short(sha: str | None) -> str:
    return (sha or "")[:10] or "—"


def _f(v, spec=".4f") -> str:
    return "—" if v is None else format(v, spec)


def render(runs: list[dict], classifier_report: dict, system_reports: dict[str, dict]) -> str:
    clf = [r for r in runs if r["experiment"] == "intent-classifier"]
    sysruns = [r for r in runs if r["experiment"] == "system-eval"]
    shas = sorted({r["tags"].get("git_sha", "unknown") for r in runs})
    dirty = sorted({r["tags"].get("git_dirty", "unknown") for r in runs})
    L = ["# ML experiment tracking: a snapshot of the MLflow runs", "",
         "The MLflow store is local and git-ignored, so this page is the part of it a reader of the repository can see. "
         f"Snapshot of {len(runs)} top-level runs ({len(clf)} classifier selection, {len(sysruns)} system evaluations), "
         f"made with code at `{', '.join(shas)}` (uncommitted changes: `{', '.join(dirty)}`), from the first run at {min(r['started'] for r in runs)} "
         f"to the last at {max(r['started'] for r in runs)} (UTC).", "",
         "Generated by `python -m eval.tracking_report`. Reproduce the runs with `make train-eval`, `make eval` and `make eval-adversarial`, "
         "then `make mlflow-ui` to browse them or `make tracking-report` to regenerate this page.", "",
         "**What is not in it:** the live-model runs (`make eval-live`), because they need API keys and billing that were not used to make this snapshot. "
         "Their results are in `eval/reports/SYSTEM_EVAL_LIVE.md` but were not tracked here.", ""]
    L += ["## Intent classifier: model selection", "",
          "One run per selection: a child run per candidate representation (dev macro-F1), the escalation threshold chosen on dev, the test scores (scored once), "
          "the hashes of the data it ran on, and the report and the model as artifacts.", "",
          "| Run | Code | Candidates (dev macro-F1) | Chosen | Threshold | Test accuracy | Test macro-F1 | Baseline accuracy | Guard recall | Data (train / held-out sha256) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in clf:
        cands = ", ".join(f"{c['params'].get('variant')} {_f(c['metrics'].get('dev_macro_f1'))}" for c in r["children"])
        m, p = r["metrics"], r["params"]
        L.append(f"| {r['name']} | `{r['tags'].get('git_sha')}` dirty={r['tags'].get('git_dirty')} | {cands} | {p.get('chosen_variant')} | {p.get('escalation_threshold')} | "
                 f"{_f(m.get('test_accuracy'))} | {_f(m.get('test_macro_f1'))} | {_f(m.get('test_baseline_accuracy'))} | {_f(m.get('test_guard_recall'))} | "
                 f"`{_short(p.get('train_sha256'))}` / `{_short(p.get('heldout_sha256'))}` |")
    L += ["", "## System evaluation", "",
          "One run per system and model: what ran (system, mode, provider, model), on what (the case file's hash, the prompt version and a hash of the prompt's fixed text), "
          "and its headline numbers. Offline runs bill no model calls, so no cost is logged for them.", "",
          "| Run | Mode | Cases | Safe automated resolution | Unsafe outcomes (rate) | Escalation recall | Missed escalations | Containment | Latency p50 / p95 (ms) | Prompt | Cases sha256 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sysruns:
        m, p = r["metrics"], r["params"]
        L.append(f"| {r['name']} | {p.get('llm_mode')} | {p.get('n_cases')} | {_f(m.get('safe_automated_resolution'))} | {_f(m.get('unsafe_outcomes'))} | "
                 f"{_f(m.get('escalation_recall'))} | {_f(m.get('missed_escalations_n'), '.0f')} | {_f(m.get('containment'))} | "
                 f"{_f(m.get('latency_ms_p50'), '.1f')} / {_f(m.get('latency_ms_p95'), '.1f')} | {p.get('prompt_version')} (`{_short(p.get('prompt_sha256'))}`) | `{_short(p.get('cases_sha256'))}` |")
    L += ["", "## Does each run say what its committed report says?", "",
          "Every logged headline number is compared with the one in the versioned report (`eval/reports/*.json`), to four decimals. A run that differs is a finding, not a formality.", "",
          "| Run | Compared with | Checks | Result |", "|---|---|---|---|"]
    for r in clf:
        checks = classifier_checks(r, classifier_report)
        L.append(f"| intent-classifier / {r['name']} | `eval/reports/intent_classifier.json` | {len(checks)} | " + ("all match" if all(ok for _, ok in checks)
                 else "**differs:** " + ", ".join(n for n, ok in checks if not ok)) + " |")
    for r in sysruns:
        found = report_for(r, system_reports)
        checks = system_checks(r, found[1] if found else None)
        source = f"`{found[0].as_posix()}`" if found else "no committed report names this run"
        L.append(f"| system-eval / {r['name']} | {source} | {len(checks)} | " + (
            "not compared" if not checks else "all match" if all(ok for _, ok in checks) else "**differs:** " + ", ".join(n for n, ok in checks if not ok)) + " |")
    L += ["", "All runs finished with status " + ("`FINISHED`." if all(r["status"] == "FINISHED" for r in runs) else
                                                    "; ".join(f"{r['name']}: `{r['status']}`" for r in runs if r["status"] != "FINISHED") + ".")]
    L += ["", "## Limits", "",
          "- A snapshot, not a live view: it is as old as its generation date. The store itself stays local.",
          "- Tracking records what ran and what it measured; it does not make a result better or more independent. The data behind these runs is the team-written sets described in `EVALUATION.md`.",
          "- The comparison with the reports checks the headline numbers only, not every metric each run logged.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a versioned snapshot of the MLflow runs")
    ap.add_argument("--store", default="sqlite:///" + str(Path("mlruns/mlflow.db").resolve().as_posix()))
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    runs = load_runs(a.store)
    if not runs:
        raise SystemExit(f"no runs in {a.store}: run `make train-eval`, `make eval` and `make eval-adversarial` first")
    reports = {mode: json.loads(p.read_text(encoding="utf-8")) for mode, p in SYSTEM_REPORTS.items() if p.exists()}
    text = render(runs, json.loads(CLASSIFIER_REPORT.read_text(encoding="utf-8")), reports)
    a.out.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
