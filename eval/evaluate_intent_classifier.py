"""Learned intent classifier vs. keyword baseline on an independent held-out set.

Protocol (the order matters and is part of the claim):
1. Training data = team-authored templates (eval/test_cases/build_intent_dataset.py).
   The keyword baseline's rules were written from those templates only.
2. Both were frozen, then eval/test_cases/heldout_utterances.csv was written
   with deliberately different phrasing (regional slang, abbreviations, no
   accents, code-switching) plus the 2 real request sentences found in the
   dataset's transcripts (source=dataset_transcript). It is never trained on.
3. The held-out set is split, stratified by intent, into dev and test halves
   by a fixed hash. Dev is used for model selection (representation variant)
   and for choosing the runtime escalation threshold, and for error analysis.
   Test is scored once, at the end, for the reported numbers.
Known limitation: the same team wrote training and held-out text, so shared
phrasing habits can inflate both systems' scores; see EVALUATION.md.

    python -m eval.evaluate_intent_classifier
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import sklearn
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

from agent.llm import baseline_classifier
from agent.llm.intent_classifier import VARIANTS, load_rows, train
from agent.policy.signals import contains_escalation_signal
from eval.stats import fmt, rate, zero_event_upper_bound

TRAIN = "eval/test_cases/intent_dataset.csv"
HELDOUT = "eval/test_cases/heldout_utterances.csv"
MODEL_OUT = Path("eval/models/intent_clf.joblib")
META_OUT = Path("eval/models/intent_clf_meta.json")
REPORT_JSON = Path("eval/reports/intent_classifier.json")
REPORT_MD = Path("eval/reports/intent_classifier.md")
ESC = "requires_escalation"
MAX_FALSE_ESCALATION = 0.05
THRESHOLDS = [round(0.05 * i, 2) for i in range(2, 19)]


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def dev_test_split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    by_intent = defaultdict(list)
    for r in rows:
        by_intent[r["intent"]].append(r)
    dev, test = [], []
    for items in by_intent.values():
        for i, r in enumerate(sorted(items, key=lambda r: _h(r["utterance"]))):
            (dev if i % 2 == 0 else test).append(r)
    return dev, test


def score(y_true: list[str], y_pred: list[str], rows: list[dict]) -> dict:
    labels = sorted(set(y_true) | set(y_pred))
    p, r, f, n = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    per_class = {}
    for i, lab in enumerate(labels):
        tp = sum(1 for t, q in zip(y_true, y_pred) if t == lab and q == lab)
        per_class[lab] = {"precision": round(p[i], 4), "recall": rate(tp, int(n[i])), "f1": round(f[i], 4), "support": int(n[i])}
    by = lambda key: {v: rate(sum(1 for row, t, q in zip(rows, y_true, y_pred) if row[key] == v and t == q),  # noqa: E731
                             sum(1 for row in rows if row[key] == v)) for v in sorted({row[key] for row in rows})}
    correct = sum(t == q for t, q in zip(y_true, y_pred))
    return {"accuracy": rate(correct, len(y_true)), "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4),
            "per_class": per_class, "by_language": by("language"), "by_style": by("style"), "by_source": by("source"),
            "confusion": {"labels": labels, "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()}}


def guard_metrics(rows: list[dict], flags: list[bool]) -> dict:
    pos = [f for r, f in zip(rows, flags) if r["intent"] == ESC]
    neg = [f for r, f in zip(rows, flags) if r["intent"] != ESC]
    missed = len(pos) - sum(pos)
    return {"recall": rate(sum(pos), len(pos)), "false_escalation": rate(sum(neg), len(neg)),
            "missed": missed, "missed_upper_bound_if_zero": zero_event_upper_bound(len(pos)) if missed == 0 else None}


def main() -> None:
    train_rows, held = load_rows(TRAIN), load_rows(HELDOUT)
    overlap = {r["utterance"].strip().lower() for r in train_rows} & {r["utterance"].strip().lower() for r in held}
    assert not overlap, f"held-out leaks into training: {overlap}"
    dev, test = dev_test_split(held)

    # 1) Model selection on dev only.
    variants = {}
    for v in VARIANTS:
        m = train(train_rows, v)
        pred = list(m.predict([r["utterance"] for r in dev]))
        variants[v] = {"dev_macro_f1": round(f1_score([r["intent"] for r in dev], pred, average="macro", zero_division=0), 4)}
    chosen = max(variants, key=lambda v: (variants[v]["dev_macro_f1"], v == "char"))
    model = train(train_rows, chosen)

    # 2) Escalation threshold on dev: max recall with false escalations <= 5%.
    def guard_flags(rows, tau):
        probs = model.predict_proba([r["utterance"] for r in rows])
        idx = list(model.classes_).index(ESC)
        return [contains_escalation_signal(r["utterance"]) or pr[idx] >= tau for r, pr in zip(rows, probs)]

    sweep = []
    for tau in THRESHOLDS:
        g = guard_metrics(dev, guard_flags(dev, tau))
        sweep.append({"tau": tau, "recall": g["recall"]["rate"], "false_escalation": g["false_escalation"]["rate"]})
    feasible = [s for s in sweep if s["false_escalation"] <= MAX_FALSE_ESCALATION] or sweep
    best = max(feasible, key=lambda s: (s["recall"], s["tau"]))
    tau = best["tau"]

    # 3) Score dev (for error analysis) and test (reported) once.
    def evaluate(rows):
        y = [r["intent"] for r in rows]
        base = [baseline_classifier.classify(r["utterance"]) for r in rows]
        learned = list(model.predict([r["utterance"] for r in rows]))
        lex = [contains_escalation_signal(r["utterance"]) for r in rows]
        probs = model.predict_proba([r["utterance"] for r in rows])
        idx = list(model.classes_).index(ESC)
        clf_only = [pr[idx] >= tau for pr in probs]
        return {
            "n": len(rows), "class_counts": dict(Counter(y)),
            "baseline_keywords": score(y, base, rows),
            "learned": score(y, learned, rows),
            "escalation_guard": {
                "lexicon_only": guard_metrics(rows, lex),
                "classifier_only": guard_metrics(rows, clf_only),
                "lexicon_or_classifier (runtime)": guard_metrics(rows, [a or b for a, b in zip(lex, clf_only)]),
            },
            "errors": [{"utterance": r["utterance"], "gold": g, "baseline": b, "learned": l, "language": r["language"], "style": r["style"]}
                       for r, g, b, l in zip(rows, y, base, learned) if b != g or l != g],
            # Reported, never used for tuning: escalation requests the runtime guard lets through.
            "guard_misses": [r["utterance"] for r, a, b in zip(rows, lex, clf_only) if r["intent"] == ESC and not (a or b)],
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "train=templates; held-out written after freezing train+baseline; dev=selection+threshold; test=scored once",
        "train_n": len(train_rows), "train_class_counts": dict(Counter(r["intent"] for r in train_rows)),
        "heldout_n": len(held), "dev_n": len(dev), "test_n": len(test),
        "model_selection_dev": variants, "chosen_variant": chosen,
        "threshold_sweep_dev": sweep, "escalation_threshold": tau, "max_false_escalation_constraint": MAX_FALSE_ESCALATION,
        "dev": evaluate(dev), "test": evaluate(test),
        "versions": {"sklearn": sklearn.__version__, "train_sha256": _h(Path(TRAIN).read_text()), "heldout_sha256": _h(Path(HELDOUT).read_text())},
    }
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_OUT)
    META_OUT.write_text(json.dumps({"escalation_threshold": tau, "variant": chosen, "trained_on": TRAIN, "train_n": len(train_rows),
                                    "sklearn": sklearn.__version__, "generated_at": report["generated_at"]}, indent=2))
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    REPORT_MD.write_text(to_markdown(report))
    print(REPORT_MD.read_text())


def to_markdown(r: dict) -> str:
    t, d = r["test"], r["dev"]
    rows = []
    for lab in sorted(t["learned"]["per_class"]):
        b, l = t["baseline_keywords"]["per_class"].get(lab, {}), t["learned"]["per_class"][lab]
        rows.append(f"| {lab} | {l['support']} | {fmt(b.get('recall'))} | {fmt(l['recall'])} | {b.get('f1', '')} | {l['f1']} |")
    lang = "\n".join(f"| {k} | {fmt(t['baseline_keywords']['by_language'][k])} | {fmt(v)} |" for k, v in t["learned"]["by_language"].items())
    style = "\n".join(f"| {k} | {fmt(t['baseline_keywords']['by_style'][k])} | {fmt(v)} |" for k, v in t["learned"]["by_style"].items())
    guard = "\n".join(f"| {k} | {fmt(v['recall'])} | {v['missed']} | {fmt(v['false_escalation'])} |" for k, v in t["escalation_guard"].items())
    errs = "\n".join(f"| {e['utterance']} | {e['gold']} | {e['baseline']} | {e['learned']} |" for e in d["errors"][:25])
    return f"""# Intent classifier evaluation (auto-generated)

Generated by `python -m eval.evaluate_intent_classifier` at {r['generated_at']}.
Protocol: {r['protocol']}. Intervals are Wilson 95%.

- Training set: {r['train_n']} team-authored template utterances ({', '.join(f'{k}={v}' for k, v in r['train_class_counts'].items())}).
- Held-out set: {r['heldout_n']} utterances (dev {r['dev_n']} / test {r['test_n']}), written after training data and baseline rules were frozen; 2 are real sentences from the dataset's transcripts.
- Representation chosen on dev by macro-F1: **{r['chosen_variant']}** ({', '.join(f"{k}: {v['dev_macro_f1']}" for k, v in r['model_selection_dev'].items())}).
- Runtime escalation threshold chosen on dev (max recall with false escalations ≤ {int(100 * r['max_false_escalation_constraint'])}%): **τ = {r['escalation_threshold']}**.

## Test split (scored once)
| | Keyword baseline | Learned ({r['chosen_variant']}) |
|---|---|---|
| Accuracy | {fmt(t['baseline_keywords']['accuracy'])} | {fmt(t['learned']['accuracy'])} |
| Macro-F1 | {t['baseline_keywords']['macro_f1']} | {t['learned']['macro_f1']} |

| Class | n | Baseline recall | Learned recall | Baseline F1 | Learned F1 |
|---|---|---|---|---|---|
{chr(10).join(rows)}

### By language (accuracy)
| Language | Baseline | Learned |
|---|---|---|
{lang}

### By writing style (accuracy)
| Style | Baseline | Learned |
|---|---|---|
{style}

### Escalation guard (what actually runs before the LLM)
| Guard | Recall on requires_escalation | Missed | False escalations |
|---|---|---|---|
{guard}

Escalation requests the runtime guard missed on test (reported, not tuned on): {', '.join(repr(u) for u in t['guard_misses']) or 'none'}. A miss here is a real missed escalation: the LLM has no escalate tool, so the request would end as ABSTAIN/CLARIFY. Not added to the lexicon, because that would be tuning on test.

## Dev-split error analysis (first 25 disagreements with gold)
| Utterance | Gold | Baseline | Learned |
|---|---|---|---|
{errs}
"""


if __name__ == "__main__":
    main()
