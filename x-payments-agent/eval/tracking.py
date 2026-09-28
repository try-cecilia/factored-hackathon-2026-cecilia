"""Experiment tracking in MLflow: `make mlflow-ui` shows every run side by side.

Every intent-classifier selection (`make train-eval`) and every system evaluation (`make eval`, `eval-adversarial`,
`eval-live`) becomes a run: what ran (model, effort, prompt version and a hash of the prompt's fixed text), on what
(hashes of the data), with which code (git sha, and whether the code or the inputs had uncommitted changes; the
regenerated reports do not count), every number its
report prints, and the report itself. The committed reports stay the reviewed record; the runs are how model and
prompt versions are compared over time.

- Store: sqlite at mlruns/mlflow.db, artifacts next to it (all git-ignored), unless MLFLOW_TRACKING_URI says
  otherwise. MLflow 3.16 refuses a plain-file store, and creating a new sqlite one takes about 12 s (migrations).
- Optional: the serving image does not install mlflow (requirements-tracking.txt). Without it a run is skipped with
  one line on stderr.
- Scripts track after their reports are written, and a failure here is reported, never raised: tracking cannot
  cost an evaluation its output.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from contextlib import contextmanager
from numbers import Real
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "mlruns"
_NOT_IN_A_METRIC_NAME = re.compile(r"[^/\w.\- ]")  # MLflow's rule on Windows, the strictest (Linux also takes ":")


def metric_name(key: str) -> str:
    """A name MLflow accepts on any system: only the characters it takes on Windows (the judge's
    "disclosure:foreign_data_in_reply" becomes "disclosure_foreign_data_in_reply"), and a path that stays itself when
    normalized, so an empty, "." or ".." part (a breakdown group with no name) becomes "_"."""
    return "/".join(part if part not in ("", ".", "..") else "_" for part in _NOT_IN_A_METRIC_NAME.sub("_", key).split("/"))


def numbers(values: dict) -> dict[str, float]:
    """The entries MLflow takes as metrics, under names it accepts (metric_name): numbers only, numpy's included (a
    rate over no cases is None, an undefined cost is text, and a flag is not a metric)."""
    return {metric_name(k): float(v) for k, v in values.items() if isinstance(v, Real) and not isinstance(v, bool)}


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:  # noqa: BLE001 - not a git checkout (the container), or no git
        return None


# Rewritten by `make all` with a fresh timestamp, and every evaluation rewrites its own report before it is tracked, so
# counting them would make every run dirty. The one an evaluation reads, docs/evidence/baseline_metrics.json (the
# projection's human baseline), is logged by value instead (the projection_inputs param).
GENERATED = ("eval/reports", "docs/evidence", "data/reports")


def dirty() -> str:
    """"true" when the code or a run's inputs have uncommitted changes, "false" when not, "unknown" outside a checkout."""
    status = _git("status", "--porcelain", "--untracked-files=no", "--", ".", *(f":(exclude){p}" for p in GENERATED))
    return "unknown" if status is None else str(bool(status)).lower()


def _artifact_location(uri: str, experiment: str) -> str | None:
    """Artifacts next to a local sqlite store; a tracking server keeps its own."""
    if not uri.startswith("sqlite:///"):
        return None
    return (Path(uri[len("sqlite:///"):]).resolve().parent / "artifacts" / experiment).as_uri()


@contextmanager
def run(experiment: str, run_name: str, tags: dict[str, str] | None = None):
    """The mlflow module inside an active run of `experiment`, or None when mlflow is missing or the store fails."""
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")  # MLflow 3.16 prints a hint for coding agents on import
    try:
        import mlflow
    except ImportError:
        print(f"experiment tracking skipped ({experiment}): mlflow is not installed "
              "(pip install -r requirements-tracking.txt)", file=sys.stderr)
        yield None
        return
    except Exception as exc:  # noqa: BLE001 - a broken install is a tracking failure like any other
        print(f"experiment tracking failed ({experiment}): {type(exc).__name__}: {exc}", file=sys.stderr)
        yield None
        return
    try:
        uri = os.environ.get("MLFLOW_TRACKING_URI")
        if not uri:
            STORE.mkdir(exist_ok=True)
            uri = "sqlite:///" + (STORE / "mlflow.db").as_posix()
        mlflow.set_tracking_uri(uri)  # also over a URI an earlier caller in this process set
        found = mlflow.get_experiment_by_name(experiment)
        experiment_id = found.experiment_id if found else mlflow.create_experiment(
            experiment, artifact_location=_artifact_location(uri, experiment))
        mlflow.set_experiment(experiment_id=experiment_id)  # nested runs go to the active experiment, not the parent's
        active = mlflow.start_run(experiment_id=experiment_id, run_name=run_name, tags={
            "git_sha": _git("rev-parse", "--short", "HEAD") or "unknown", "git_dirty": dirty(), **(tags or {})})
    except Exception as exc:  # noqa: BLE001 - tracking never costs an evaluation its output
        print(f"experiment tracking failed ({experiment}): {type(exc).__name__}: {exc}", file=sys.stderr)
        yield None
        return
    try:
        with active:
            yield mlflow
    except Exception as exc:  # noqa: BLE001 - the run is ended as FAILED; the evaluation's output is already written
        print(f"experiment tracking failed ({experiment}): {type(exc).__name__}: {exc}", file=sys.stderr)
