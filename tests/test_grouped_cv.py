"""The representation is chosen by template-grouped cross-validation on the training set together with dev."""
from __future__ import annotations

import json
from pathlib import Path

from agent.llm.intent_classifier import load_rows
from eval import evaluate_intent_classifier as evaluation

ROOT = Path(__file__).resolve().parent.parent


def test_the_committed_choice_is_the_best_mean_of_cross_validation_and_dev():
    report = json.loads((ROOT / "eval/reports/intent_classifier.json").read_text(encoding="utf-8"))
    scores = report["model_selection_dev"]
    assert all(s["selection_score"] == round((s["cv_macro_f1"] + s["dev_macro_f1"]) / 2, 4) for s in scores.values())
    assert report["chosen_variant"] == max(scores, key=lambda v: (scores[v]["selection_score"], v == "char"))


def test_grouped_cv_is_deterministic_and_a_template_never_sits_on_both_sides(monkeypatch):
    rows = load_rows(evaluation.TRAIN)
    monkeypatch.setattr(evaluation, "CV_REPEATS", 2)
    mean, std = evaluation.grouped_cv_macro_f1(rows, "char")
    assert (mean, std) == evaluation.grouped_cv_macro_f1(rows, "char") and 0.5 < mean <= 1
    # the folds it uses: no template id in both the fitting and the held-out side
    X, y, groups = [r["utterance"] for r in rows], [r["intent"] for r in rows], [r["template_id"] for r in rows]
    for fit, held in evaluation.StratifiedGroupKFold(evaluation.CV_FOLDS, shuffle=True, random_state=0).split(X, y, groups):
        assert not {groups[i] for i in fit} & {groups[i] for i in held}
