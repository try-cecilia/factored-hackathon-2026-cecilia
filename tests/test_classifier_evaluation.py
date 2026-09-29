"""Every section of the classifier report must score the model and threshold being selected."""
from __future__ import annotations

import pytest

from agent.policy import intent_guard
from eval import evaluate_intent_classifier as evaluation


@pytest.mark.parametrize("probability, threshold, expected", [(0.6, 0.5, 2), (0.6, 0.7, 1), (0.4, 0.5, 1)])
def test_trace_guard_uses_the_supplied_model_and_threshold_and_preserves_keyword_escalation(
        tmp_path, monkeypatch, probability, threshold, expected):
    heldout = tmp_path / "traces.csv"
    heldout.write_text("utterance\nNecesito rastrear una transferencia\nMe robaron la tarjeta\n", encoding="utf-8")
    monkeypatch.setattr(evaluation, "TRACE_HELDOUT", str(heldout))
    # A stale deployment model must not contribute to the new model's report.
    monkeypatch.setattr(intent_guard, "_load", lambda: pytest.fail("read the deployment model"))

    class Candidate:
        classes_ = [evaluation.ESC, "other"]

        def predict_proba(self, texts):
            return [[probability, 1 - probability], [0.0, 1.0]]

    report = evaluation.trace_guard(Candidate(), threshold)
    assert report["n"] == 2 and report["handed_to_a_person"]["k"] == expected
    assert "Me robaron la tarjeta" in report["utterances"]
