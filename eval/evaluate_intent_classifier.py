"""Baseline vs. learned intent classifier, evaluated on the same held-out split.

Split is by template_id, not by row: several utterances share a template
(only the slot values differ), so splitting by row would leak near-duplicate
sentences into both train and test. Splitting by template_id guarantees the
test set contains phrasings the model never saw during training.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from sklearn.metrics import classification_report

from agent.llm import baseline_classifier
from agent.llm.intent_classifier import load_dataset, train

TEST_FRACTION = 0.3


def template_split(rows: list[dict], test_fraction: float = TEST_FRACTION) -> tuple[list[dict], list[dict]]:
    template_ids = sorted({r["template_id"] for r in rows})
    # Deterministic pseudo-random split via hash, not random.shuffle, so
    # re-running this script always reproduces the same split.
    import hashlib

    def bucket(tid: str) -> float:
        return int(hashlib.sha256(tid.encode()).hexdigest(), 16) % 1000 / 1000

    test_templates = {t for t in template_ids if bucket(t) < test_fraction}
    train_rows = [r for r in rows if r["template_id"] not in test_templates]
    test_rows = [r for r in rows if r["template_id"] in test_templates]
    return train_rows, test_rows


def evaluate() -> dict:
    rows = load_dataset()
    train_rows, test_rows = template_split(rows)
    assert train_rows and test_rows, "split produced an empty train or test set"

    pipeline = train(train_rows)

    y_true = [r["intent"] for r in test_rows]
    y_pred_baseline = [baseline_classifier.classify(r["utterance"]) for r in test_rows]
    y_pred_proposed = list(pipeline.predict([r["utterance"] for r in test_rows]))

    report = {
        "n_train": len(train_rows),
        "n_test": len(test_rows),
        "train_templates": sorted({r["template_id"] for r in train_rows}),
        "test_templates": sorted({r["template_id"] for r in test_rows}),
        "baseline": classification_report(y_true, y_pred_baseline, output_dict=True, zero_division=0),
        "proposed": classification_report(y_true, y_pred_proposed, output_dict=True, zero_division=0),
    }

    # Escalation recall gets its own explicit callout: a missed escalation
    # (false negative on requires_escalation) is the costliest error class
    # in this workflow, more so than lower accuracy elsewhere.
    report["requires_escalation_recall"] = {
        "baseline": report["baseline"].get("requires_escalation", {}).get("recall", 0.0),
        "proposed": report["proposed"].get("requires_escalation", {}).get("recall", 0.0),
    }

    by_language = defaultdict(list)
    for r, pred in zip(test_rows, y_pred_proposed):
        by_language[r["language"]].append(1 if pred == r["intent"] else 0)
    report["proposed_accuracy_by_language"] = {
        lang: round(sum(v) / len(v), 4) for lang, v in by_language.items()
    }

    return report


if __name__ == "__main__":
    report = evaluate()
    out_path = Path("eval/intent_classifier_report.json")
    out_path.write_text(json.dumps(report, indent=2))
    print(f"n_train={report['n_train']} n_test={report['n_test']}")
    print("baseline accuracy:", report["baseline"]["accuracy"])
    print("proposed accuracy:", report["proposed"]["accuracy"])
    print("requires_escalation recall (baseline vs proposed):", report["requires_escalation_recall"])
    print("proposed accuracy by language:", report["proposed_accuracy_by_language"])
    print(f"Full report written to {out_path}")
