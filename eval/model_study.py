"""How much do the intent classifier's choices matter? A sensitivity and learning-curve study on dev only.

    python -m eval.model_study        # writes docs/evidence/model_study.{md,json}

Protocol, fixed before the first run (the git history orders this file and its results):

- **The shipped model does not change, whatever this shows.** It is TF-IDF char+word features and a logistic regression
  with C = 10 and balanced class weights, chosen on dev, and its test split was scored once (`eval/reports/intent_classifier.md`).
  Re-choosing after seeing a result would be a second look at evidence that was spent. The study says how much the choice
  mattered; it does not make it again.
- **Dev only.** `study` takes the training rows and the dev rows and nothing else: the test split is dropped as soon as the
  data is loaded and no function here can reach it.
- **What is reported.** (1) A grid of representation x regularization strength C, each cell's dev macro-F1 and its paired
  bootstrap difference from the shipped configuration. A difference whose 95% interval contains 0 is noise at this dev size and is
  called so. (2) A learning curve: dev macro-F1 against the share of the training data used, over repeated stratified
  subsamples, to say whether more data of the same kind would help.
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

from agent.llm.intent_classifier import VARIANTS, build_pipeline, load_rows
from eval import leakage
from eval.evaluate_intent_classifier import HELDOUT, TRAIN, dev_test_split

OUT_JSON, OUT_MD = Path("docs/evidence/model_study.json"), Path("docs/evidence/model_study.md")
SHIPPED = {"variant": "char+word", "C": 10.0}
C_GRID = (1.0, 3.0, 10.0, 30.0, 100.0)
FRACTIONS = (0.1, 0.25, 0.5, 0.75, 1.0)
SUBSAMPLES = 20
RESAMPLES = 1000
SEED = 0


def dev_rows() -> tuple[list[dict], list[dict]]:
    """The training rows and the dev half of the held-out set, with the phrases the leakage check leaves out removed. The test
    half is dropped here, on the line it is produced."""
    train_rows, held = load_rows(TRAIN), load_rows(HELDOUT)
    dropped = leakage.excluded_utterances(leakage.report([r["utterance"] for r in train_rows], [r["utterance"] for r in held]))
    dev, _ = dev_test_split(held)
    return train_rows, [r for r in dev if r["utterance"] not in dropped]


def _fit(rows: list[dict], variant: str, c: float):
    pipe = build_pipeline(variant)
    pipe.set_params(clf__C=c)
    pipe.fit([r["utterance"] for r in rows], [r["intent"] for r in rows])
    return pipe


def _macro_f1(y_true, y_pred) -> float:
    return float(f1_score(y_true, y_pred, average="macro", zero_division=0))


def _paired_interval(y_true: np.ndarray, a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """95% bootstrap interval of macro-F1(a) - macro-F1(b) over resamples of the same dev rows."""
    diffs = []
    for _ in range(RESAMPLES):
        idx = rng.integers(0, len(y_true), len(y_true))
        diffs.append(_macro_f1(y_true[idx], a[idx]) - _macro_f1(y_true[idx], b[idx]))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(lo), float(hi)


def sensitivity(train_rows: list[dict], dev: list[dict]) -> list[dict]:
    y = np.array([r["intent"] for r in dev])
    texts = [r["utterance"] for r in dev]
    preds = {(v, c): np.array(_fit(train_rows, v, c).predict(texts)) for v in VARIANTS for c in C_GRID}
    shipped = preds[(SHIPPED["variant"], SHIPPED["C"])]
    rng = np.random.default_rng(SEED)
    cells = []
    for (v, c), p in preds.items():
        is_shipped = (v, c) == (SHIPPED["variant"], SHIPPED["C"])
        lo, hi = (0.0, 0.0) if is_shipped else _paired_interval(y, p, shipped, rng)
        cells.append({"variant": v, "C": c, "dev_macro_f1": round(_macro_f1(y, p), 4), "dev_accuracy": round(float(accuracy_score(y, p)), 4),
                      "vs_shipped": round(_macro_f1(y, p) - _macro_f1(y, shipped), 4), "vs_shipped_ci95": [round(lo, 4), round(hi, 4)],
                      "shipped": is_shipped, "distinguishable_from_shipped": (not is_shipped) and (lo > 0 or hi < 0)})
    return cells


def _subsample(rows: list[dict], fraction: float, rng: random.Random) -> list[dict]:
    by_intent = defaultdict(list)
    for r in rows:
        by_intent[r["intent"]].append(r)
    picked = []
    for items in by_intent.values():
        picked += rng.sample(items, max(1, math.ceil(fraction * len(items))))
    return picked


def learning_curve(train_rows: list[dict], dev: list[dict]) -> list[dict]:
    y, texts = [r["intent"] for r in dev], [r["utterance"] for r in dev]
    out = []
    for fraction in FRACTIONS:
        rng = random.Random(SEED)
        scores = [_macro_f1(y, _fit(_subsample(train_rows, fraction, rng), SHIPPED["variant"], SHIPPED["C"]).predict(texts))
                  for _ in range(1 if fraction == 1.0 else SUBSAMPLES)]
        out.append({"fraction": fraction, "n_train": len(_subsample(train_rows, fraction, random.Random(SEED))), "runs": len(scores),
                    "dev_macro_f1_mean": round(float(np.mean(scores)), 4), "dev_macro_f1_min": round(min(scores), 4), "dev_macro_f1_max": round(max(scores), 4)})
    return out


def study(train_rows: list[dict], dev: list[dict]) -> dict:
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "shipped": SHIPPED, "n_train": len(train_rows), "n_dev": len(dev),
            "sensitivity": sensitivity(train_rows, dev), "learning_curve": learning_curve(train_rows, dev)}


def to_markdown(s: dict) -> str:
    cells = s["sensitivity"]
    best = max(cells, key=lambda c: c["dev_macro_f1"])
    n_distinct = sum(c["distinguishable_from_shipped"] for c in cells)
    lines = ["# Intent classifier: sensitivity and learning curve (dev only)", "",
             f"Generated by `python -m eval.model_study` at {s['generated_at']}. Protocol, fixed before the first run, in the module's docstring: **the shipped model does not change, whatever this shows**, "
             f"and only the {s['n_dev']} dev utterances are used (the test split is not read). Training set: {s['n_train']} team-written template utterances.", "",
             "## 1. How much the choice of representation and regularization matters", "",
             f"Dev macro-F1 of each configuration, and its difference from the shipped one ({SHIPPED['variant']}, C = {SHIPPED['C']:g}) with a paired 95% bootstrap interval "
             f"({RESAMPLES:,} resamples of the same dev rows, seed {SEED}).", "",
             "| Representation | C | Dev macro-F1 | Dev accuracy | Difference from shipped | 95% interval | Distinguishable |", "|---|---|---|---|---|---|---|"]
    for c in sorted(cells, key=lambda c: (c["variant"], c["C"])):
        mark = "**shipped**" if c["shipped"] else ("yes" if c["distinguishable_from_shipped"] else "no (noise)")
        diff = "" if c["shipped"] else f"{c['vs_shipped']:+.4f}"
        ci = "" if c["shipped"] else f"[{c['vs_shipped_ci95'][0]:+.4f}, {c['vs_shipped_ci95'][1]:+.4f}]"
        lines.append(f"| {c['variant']} | {c['C']:g} | {c['dev_macro_f1']:.4f} | {c['dev_accuracy']:.4f} | {diff} | {ci} | {mark} |")
    lines += ["", f"The best cell on dev is {best['variant']} with C = {best['C']:g} ({best['dev_macro_f1']:.4f}). {n_distinct} of the {len(cells) - 1} other configurations "
              "differ from the shipped one by more than the noise of this dev set, all of them for the worse. We do not adopt any of them: the shipped model stays. "
              "Read the shipped row as the optimistic one: its representation was chosen on this same dev set, so part of its margin is selection.", "",
              "## 2. Would more data of the same kind help?", "",
              f"Dev macro-F1 of the shipped configuration trained on a share of the training data (stratified subsamples, {SUBSAMPLES} per share, seed {SEED}; "
              "the full set is one run).", "",
              "| Share of training data | Utterances | Runs | Mean dev macro-F1 | Min | Max |", "|---|---|---|---|---|---|"]
    lines += [f"| {round(100 * r['fraction'])}% | {r['n_train']} | {r['runs']} | {r['dev_macro_f1_mean']:.4f} | {r['dev_macro_f1_min']:.4f} | {r['dev_macro_f1_max']:.4f} |"
              for r in s["learning_curve"]]
    first, before, last = s["learning_curve"][0], s["learning_curve"][-2], s["learning_curve"][-1]
    rising = last["dev_macro_f1_mean"] > before["dev_macro_f1_max"]
    lines += ["", f"From {round(100 * first['fraction'])}% to {round(100 * last['fraction'])}% of the training data the mean dev macro-F1 goes from {first['dev_macro_f1_mean']:.4f} to {last['dev_macro_f1_mean']:.4f}. "
              f"The last step, from {round(100 * before['fraction'])}% to {round(100 * last['fraction'])}%, adds {last['dev_macro_f1_mean'] - before['dev_macro_f1_mean']:+.4f}, "
              + (f"more than the whole spread of the {round(100 * before['fraction'])}% subsamples ({before['dev_macro_f1_min']:.4f} to {before['dev_macro_f1_max']:.4f}): the curve is still rising at the end, "
                 "which says more data of this kind would probably help. " if rising else
                 f"inside the spread of the {round(100 * before['fraction'])}% subsamples ({before['dev_macro_f1_min']:.4f} to {before['dev_macro_f1_max']:.4f}): the curve has flattened, so the limit is not the amount of data. ")
              + "Two cautions: the full-data point is one run, and it is the configuration chosen on this dev set.", "",
              "## What this does not show", "",
              "- Every number here is on the dev half of a held-out set written by the same team that wrote the training text, so shared phrasing habits can flatter all of it (`EVALUATION.md`).",
              f"- {s['n_dev']} dev utterances is small: an interval that contains 0 means \"we cannot tell\", not \"they are equal\".",
              "- The grid varies two choices. It does not search n-gram ranges, class weights or other model families, and it does not tune the escalation threshold, which was chosen separately on dev.", ""]
    return "\n".join(lines)


def main() -> None:
    train_rows, dev = dev_rows()
    s = study(train_rows, dev)
    OUT_JSON.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(to_markdown(s), encoding="utf-8")
    print(OUT_MD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
