"""Is P(requires_escalation) a probability? Reliability table and ECE around the runtime threshold (tau, chosen on dev).

    python -m eval.calibration      # trains as eval.evaluate_intent_classifier does, writes eval/reports/CALIBRATION.md

The guard hands a message to a person when P(requires_escalation) >= tau. This asks whether that number means what it says: of the
held-out utterances the model gives ~0.7, are ~70% really escalations? Nothing is fitted or re-chosen here: the model, the dev/test split
and tau are the ones eval.evaluate_intent_classifier produces. Test is the headline; dev + test pooled is shown because test alone has
few escalations (the intervals say how few).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from agent.llm.intent_classifier import load_rows
from eval import leakage
from eval.evaluate_intent_classifier import ESC, HELDOUT, TRAIN, build_report, dev_test_split
from eval.stats import wilson

OUT = Path("eval/reports/CALIBRATION.md")
EDGES = [0.0, 0.1, 0.3, 0.55, 0.8, 1.0000001]  # 0.55 is an edge so the table has a bin that starts at the runtime threshold
RESAMPLES = 2000
SEED = 0


def reliability(p: np.ndarray, y: np.ndarray, edges: list[float]) -> tuple[list[dict], float]:
    """Per-bin n, mean predicted, observed rate; ECE = sum over bins of (n_bin / N) * |observed - predicted|."""
    rows, ece = [], 0.0
    for lo, hi in zip(edges, edges[1:]):
        m = (p >= lo) & (p < hi)
        if m.any():
            conf, acc = float(p[m].mean()), float(y[m].mean())
            ece += m.sum() / len(p) * abs(acc - conf)
            rows.append({"lo": lo, "hi": min(hi, 1.0), "n": int(m.sum()), "pos": int(y[m].sum()), "conf": conf, "acc": acc, "ci": wilson(int(y[m].sum()), int(m.sum()))})
    return rows, float(ece)


def ece_interval(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    e = [reliability(p[i], y[i], EDGES)[1] for i in (rng.integers(0, len(p), len(p)) for _ in range(RESAMPLES))]
    return float(np.percentile(e, 2.5)), float(np.percentile(e, 97.5))


def top_label_ece(probs: np.ndarray, y_idx: np.ndarray) -> float:
    """The usual multiclass ECE: confidence is the largest probability, 'observed' is whether that class was right."""
    conf, hit = probs.max(axis=1), (probs.argmax(axis=1) == y_idx).astype(float)
    return reliability(conf, hit, [0.0, 0.4, 0.55, 0.7, 0.85, 1.0000001])[1]


def section(title: str, p: np.ndarray, y: np.ndarray, probs: np.ndarray, y_idx: np.ndarray, tau: float) -> list[str]:
    table, ece = reliability(p, y, EDGES)
    lo, hi = ece_interval(p, y)
    flagged = p >= tau
    tp, fp = int((flagged & y).sum()), int((flagged & ~y).sum())
    fmt = lambda k, n: f"{k}/{n} = {k / max(n, 1):.1%} [{wilson(k, n)[0]:.1%}-{wilson(k, n)[1]:.1%}]"  # noqa: E731
    return [f"## {title}", "",
            f"n = {len(p)}, {int(y.sum())} escalations. **ECE of P(requires_escalation) = {ece:.3f}** (95% bootstrap [{lo:.3f}, {hi:.3f}], {RESAMPLES:,} resamples); "
            f"Brier {float(np.mean((p - y) ** 2)):.3f}; top-label ECE over all six intents {top_label_ece(probs, y_idx):.3f}.", "",
            "| P(escalation) bin | n | Mean predicted | Observed escalations (Wilson 95%) |", "|---|---|---|---|",
            *[f"| [{r['lo']:.2f}, {r['hi']:.2f}) | {r['n']} | {r['conf']:.2f} | {r['pos']}/{r['n']} = {r['acc']:.0%} [{r['ci'][0]:.0%}-{r['ci'][1]:.0%}] |" for r in table], "",
            f"At tau = {tau} (classifier alone, without the lexicon): precision {fmt(tp, tp + fp)}; recall {fmt(tp, int(y.sum()))}; "
            f"false escalations {fmt(fp, int((~y).sum()))}.", ""]


def main() -> None:
    train_rows, held = load_rows(TRAIN), load_rows(HELDOUT)
    report, model = build_report(train_rows, held)
    tau, idx = report["escalation_threshold"], list(model.classes_).index(ESC)
    dropped = leakage.excluded_utterances(report["leakage"])
    dev, test = (([r for r in split if r["utterance"] not in dropped]) for split in dev_test_split(held))

    def arrays(rows):
        probs = model.predict_proba([r["utterance"] for r in rows])
        return probs[:, idx], np.array([r["intent"] == ESC for r in rows]), probs, np.array([list(model.classes_).index(r["intent"]) for r in rows])

    t, d = arrays(test), arrays(dev)
    pooled = tuple(np.concatenate([a, b]) for a, b in zip(t, d))
    lines = ["# Calibration of the escalation probability (auto-generated)", "",
             f"`python -m eval.calibration`. The runtime guard escalates when P(requires_escalation) >= tau = {tau}, a value chosen on dev "
             "(max recall with false escalations <= 5%). Model, split and tau are the ones `eval.evaluate_intent_classifier` produces; "
             "nothing is re-fitted or re-chosen here. Held-out utterances are team-written (LIMITATIONS.md).", "",
             *section("Test split (scored once)", *t, tau),
             *section("Dev + test pooled (more escalations, but dev chose tau, so read it as descriptive)", *pooled, tau)]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
