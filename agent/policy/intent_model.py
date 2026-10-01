"""The intent classifier as plain JSON, scored in pure Python (no scikit-learn, no pickle at runtime).

`export` is called by the trainer (eval/evaluate_intent_classifier.py) on the fitted pipeline; `predict_proba` is what the
server runs. A JSON file can only hold data, so a tampered model can change an answer but cannot execute code on load
(ASVS V5.5.3). It re-implements exactly what the pipeline does: sklearn's `char_wb` / word analyzers, sublinear tf x idf,
L2 norm per vectorizer, then a multinomial logistic regression. tests/test_intent_model.py pins it to sklearn.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from agent.policy.signals import normalize

FORMAT = 1
_WORD = re.compile(r"(?u)\b\w\w+\b")  # sklearn's default token_pattern
_DECIMALS = 8  # weights rounded here: the JSON stays small and the probabilities move by < 1e-6


def export(model) -> dict:
    """The fitted `Pipeline(features -> clf)` of agent/llm/intent_classifier.py as a JSON-able dict."""
    features, clf = model.named_steps["features"], model.named_steps["clf"]
    vectorizers = [v for _, v in features.transformer_list] if hasattr(features, "transformer_list") else [features]
    assert len(clf.classes_) > 2 and clf.coef_.shape[0] == len(clf.classes_), "softmax scorer: needs 3+ classes"
    out, offset = [], 0
    for v in vectorizers:
        # term -> [idf, weight of that term for each class]; the terms of a vectorizer are one block of coef_ columns
        vocab = {t: [round(float(v.idf_[i]), _DECIMALS)] + [round(float(w), _DECIMALS) for w in clf.coef_[:, offset + i]]
                 for t, i in sorted(v.vocabulary_.items(), key=lambda kv: kv[1])}
        out.append({"analyzer": v.analyzer, "ngram_range": list(v.ngram_range), "vocab": vocab})
        offset += len(v.vocabulary_)
    return {"format": FORMAT, "classes": [str(c) for c in clf.classes_],
            "intercept": [round(float(b), _DECIMALS) for b in clf.intercept_], "vectorizers": out}


def _terms(analyzer: str, ngram_range, text: str):
    lo, hi = ngram_range
    if analyzer == "char_wb":
        for word in text.split():
            word = f" {word} "
            for n in range(lo, hi + 1):
                for i in range(max(len(word) - n + 1, 1)):
                    yield word[i:i + n]
                if len(word) <= n:  # sklearn stops growing the n-gram once it is the whole padded word
                    break
    elif analyzer == "word":
        tokens = _WORD.findall(text)
        for n in range(lo, min(hi, len(tokens)) + 1):
            for i in range(len(tokens) - n + 1):
                yield " ".join(tokens[i:i + n])
    else:
        raise ValueError(f"unsupported analyzer {analyzer!r}")


def predict_proba(spec: dict, text: str) -> dict[str, float]:
    """P(class | text), the same numbers as `Pipeline.predict_proba([text])`."""
    if spec.get("format") != FORMAT:
        raise ValueError(f"intent model format {spec.get('format')!r}, expected {FORMAT}")
    text = normalize(text)
    logits = list(spec["intercept"])
    for v in spec["vectorizers"]:
        vocab = v["vocab"]
        counts = Counter(t for t in _terms(v["analyzer"], v["ngram_range"], text) if t in vocab)
        tfidf = {t: (1 + math.log(c)) * vocab[t][0] for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in tfidf.values())) or 1.0
        for t, x in tfidf.items():
            for k, w in enumerate(vocab[t][1:]):
                logits[k] += x / norm * w
    top = max(logits)
    exp = [math.exp(z - top) for z in logits]
    total = sum(exp)
    return {c: e / total for c, e in zip(spec["classes"], exp)}
