"""Runtime use of the learned intent classifier.

Two jobs, both deterministic given the model file:
1. Escalation OR-guard: escalate before any LLM call if the keyword lexicon
   fires OR P(requires_escalation) >= threshold. The threshold is chosen on
   the dev split for recall (eval/evaluate_intent_classifier.py writes it to
   eval/models/intent_clf_meta.json) and is never tuned on the test split.
2. ABSTAIN vs CLARIFY when the LLM answers without calling a tool: the
   classifier's out_of_scope prediction decides, instead of the old
   "response contains a question mark" heuristic.
If the model file is missing, both degrade to keyword-only behavior and the
degradation is logged, never silently ignored.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from agent.policy import intent_model

logger = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("INTENT_MODEL_PATH", "eval/models/intent_clf.json")
META_PATH = os.environ.get("INTENT_META_PATH", "eval/models/intent_clf_meta.json")
DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class IntentReading:
    intent: str | None
    p_intent: float | None
    p_escalation: float | None
    p_out_of_scope: float | None
    threshold: float
    model_available: bool

    @property
    def escalate(self) -> bool:
        return self.p_escalation is not None and self.p_escalation >= self.threshold


@lru_cache(maxsize=1)
def _load():
    if not Path(MODEL_PATH).exists():
        logger.warning("intent classifier not found at %s; escalation guard is keyword-only", MODEL_PATH)
        return None, DEFAULT_THRESHOLD
    threshold = DEFAULT_THRESHOLD
    if Path(META_PATH).exists():
        threshold = float(json.loads(Path(META_PATH).read_text(encoding="utf-8")).get("escalation_threshold", DEFAULT_THRESHOLD))
    return json.loads(Path(MODEL_PATH).read_text(encoding="utf-8")), threshold


def read(text: str) -> IntentReading:
    model, threshold = _load()
    if model is None:
        return IntentReading(None, None, None, None, threshold, False)
    probs = intent_model.predict_proba(model, text)
    intent = max(probs, key=probs.get)
    return IntentReading(str(intent), float(probs[intent]), float(probs.get("requires_escalation", 0.0)),
                         float(probs.get("out_of_scope", 0.0)), threshold, True)


def reset_cache() -> None:
    _load.cache_clear()
