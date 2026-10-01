"""The JSON model that the server scores in pure Python gives the scikit-learn pipeline's probabilities."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from agent.llm.intent_classifier import load_rows
from agent.policy import intent_guard, intent_model
from eval import evaluate_intent_classifier as evaluation

ROOT = Path(__file__).resolve().parent.parent
TOL = 1e-5  # the weights are rounded to 8 decimals in the file


def test_the_json_model_matches_the_sklearn_model_it_was_exported_from():
    sk = joblib.load(  # our own committed model, the reference; the server never loads it
        ROOT / "eval/models/intent_clf.joblib")
    spec = json.loads((ROOT / "eval/models/intent_clf.json").read_text(encoding="utf-8"))
    texts = [r["utterance"] for r in load_rows(evaluation.HELDOUT) + load_rows(evaluation.TRAIN)]
    texts += ["", "   ", "q saldo tengo?", "ñandú 😀 ÁÉÍ", "a", "x" * 300]  # no known term, accents, emoji, a very long word
    want = sk.predict_proba(texts)
    got = np.array([[intent_model.predict_proba(spec, t)[c] for c in sk.classes_] for t in texts])
    assert list(sk.classes_) == spec["classes"]
    assert np.abs(want - got).max() < TOL


def test_the_server_loads_the_json_and_the_guard_reads_it(monkeypatch):
    monkeypatch.setattr(intent_guard, "MODEL_PATH", str(ROOT / "eval/models/intent_clf.json"))
    intent_guard.reset_cache()
    try:
        reading = intent_guard.read("me robaron la tarjeta")
        assert reading.model_available and reading.intent and 0 < reading.p_intent <= 1
    finally:
        intent_guard.reset_cache()


def test_a_model_of_another_format_is_refused():
    try:
        intent_model.predict_proba({"format": 99}, "hola")
    except ValueError:
        return
    raise AssertionError("an unknown format must not be scored")
