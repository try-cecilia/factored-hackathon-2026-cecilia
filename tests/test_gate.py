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
