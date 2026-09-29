"""Learned intent classifier: TF-IDF n-grams + Logistic Regression.

Representation: candidates are character n-grams, word n-grams, or both;
the variant is chosen on the held-out *dev* split by macro-F1
(eval/evaluate_intent_classifier.py) and the choice is recorded in the model
metadata. Character n-grams are the expected winner because they are robust
to what real customers type — missing accents, abbreviations ("q saldo",
"qto"), regional spellings — and they need no pretrained weights (this
project's build environment can't download embedding models; see
LIMITATIONS.md). Class-balanced weights offset the smaller out_of_scope and
requires_escalation classes.
"""
from __future__ import annotations

import csv

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from agent.policy.signals import normalize

VARIANTS = ("char", "word", "char+word")


def load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_pipeline(variant: str = "char") -> Pipeline:
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, preprocessor=normalize)
    word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, preprocessor=normalize)
    features = {"char": char, "word": word, "char+word": FeatureUnion([("char", char), ("word", word)])}[variant]
    return Pipeline([("features", features),
                     ("clf", LogisticRegression(max_iter=3000, C=10.0, class_weight="balanced"))])


def train(rows: list[dict], variant: str = "char") -> Pipeline:
    p = build_pipeline(variant)
    p.fit([r["utterance"] for r in rows], [r["intent"] for r in rows])
    return p
