"""Does the behavioral composite say anything about `is_fraud`? The protocol is section 5 of docs/BEHAVIORAL_EVIDENCE.md.

    python -m analysis.behavior_association    # reads DUCKDB_PATH (the full warehouse), writes docs/evidence/behavior_association.md

Association reporting only: nothing is fitted, so the formulas fixed before this ran are scored as they are. The wording
the result allows is decided by the gates in section 6, applied in `verdict`; a miss is not repaired by changing a formula.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
from sklearn.metrics import roc_auc_score

from agent.policy.behavior import COMPONENTS, score_customer

OUT = Path("docs/evidence/behavior_association.md")
OTHER_CUSTOMERS = 20_000
RESAMPLES = 1_000
SEED = 0
COLUMNS = "transaction_id, customer_id, transaction_date, amount, currency, channel, merchant_category, transaction_country, is_fraud, fraud_score"


def auc_from_bins(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUC from counts per score bin, ties counting half: what lets the bootstrap resample a histogram instead of 4M rows."""
    below = np.cumsum(neg) - neg
    return float((pos * (below + neg / 2)).sum() / (pos.sum() * neg.sum()))


def bootstrap_interval(pos: np.ndarray, neg: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """Stratified: frauds and legitimate rows are resampled separately, each from its own distribution over the bins."""
    aucs = [auc_from_bins(rng.multinomial(pos.sum(), pos / pos.sum()), rng.multinomial(neg.sum(), neg / neg.sum())) for _ in range(RESAMPLES)]
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    return float(lo), float(hi)


def verdict(lower: float, point: float) -> str:
    """Section 6 of the contract: what we are allowed to say."""
    if lower <= 0.55:
        return "No detectable association with the `is_fraud` label."
    if lower >= 0.60:
        return "Association with a synthetic label; not validation against real fraud."
    return "Weak association with a synthetic label; not validation against real fraud." if point < 0.65 else "Association with a synthetic label; not validation against real fraud."


def main() -> None:
    con = duckdb.connect(os.environ.get("DUCKDB_PATH", "data/warehouse/full.duckdb"), read_only=True)
    con.execute(f"""CREATE TEMP TABLE picked AS
        SELECT DISTINCT customer_id FROM transactions WHERE is_fraud
        UNION
        SELECT customer_id FROM (SELECT DISTINCT customer_id FROM transactions
                                 WHERE customer_id NOT IN (SELECT customer_id FROM transactions WHERE is_fraud))
                                USING SAMPLE reservoir({OTHER_CUSTOMERS} ROWS) REPEATABLE ({SEED})""")
    # read these first: a later execute on the connection replaces the result the cursor is still streaming
    fraud_customers = con.execute("SELECT count(DISTINCT customer_id) FROM transactions WHERE is_fraud").fetchone()[0]
    total_fraud = con.execute("SELECT count(*) FROM transactions WHERE is_fraud AND customer_id IN (SELECT customer_id FROM picked)").fetchone()[0]
    cursor = con.execute(f"SELECT {COLUMNS} FROM transactions WHERE customer_id IN (SELECT customer_id FROM picked) ORDER BY customer_id")
    names = [d[0] for d in cursor.description]

    y, composite, score = [], [], []
    comp = {c: ([], []) for c in COMPONENTS}  # component value, label
    rows_total = 0
    current, group = None, []

    def flush() -> None:
        nonlocal rows_total
        if not group:
            return
        scored = score_customer(group)
        for r in group:
            rows_total += 1
            s = scored[r["transaction_id"]]
            label = bool(r["is_fraud"])
            for c, v in s["components"].items():
                if v is not None:
                    comp[c][0].append(v); comp[c][1].append(label)
            if s["composite"] is not None:
                y.append(label); composite.append(s["composite"])
                score.append(None if r["fraud_score"] is None else float(r["fraud_score"]))

    while batch := cursor.fetchmany(200_000):
        for values in batch:
            r = dict(zip(names, values))
            if r["customer_id"] != current:
                flush(); current, group = r["customer_id"], []
            group.append(r)
    flush()

    y_arr, comp_arr = np.array(y, dtype=bool), np.array(composite)
    pos = np.bincount(np.rint(comp_arr[y_arr] * 10).astype(int), minlength=1001)
    neg = np.bincount(np.rint(comp_arr[~y_arr] * 10).astype(int), minlength=1001)
    auc = auc_from_bins(pos, neg)
    lo, hi = bootstrap_interval(pos, neg, np.random.default_rng(SEED))

    has_score = np.array([s is not None for s in score])
    fs_auc = roc_auc_score(y_arr[has_score], np.array([s for s in score if s is not None]))
    comp_auc = {c: (roc_auc_score(labels, values) if len(set(labels)) == 2 else float("nan"), len(values), int(sum(labels)))
                for c, (values, labels) in comp.items()}

    lines = [
        "# Behavioral composite against `is_fraud` (auto-generated)", "",
        f"`python -m analysis.behavior_association` at {datetime.now(timezone.utc).isoformat(timespec='seconds')} on the full warehouse. "
        "Protocol and wording gates: [`docs/BEHAVIORAL_EVIDENCE.md`](../BEHAVIORAL_EVIDENCE.md), frozen before this ran. Nothing was fitted.", "",
        "## Population", "",
        f"- Every one of the {fraud_customers:,} customers with a fraud transaction, plus {OTHER_CUSTOMERS:,} others (seed {SEED}): {rows_total:,} transactions, {total_fraud:,} of them fraud.",
        f"- A composite exists for {len(y_arr):,} of them ({len(y_arr) / rows_total:.1%}), including {int(y_arr.sum()):,} of the {total_fraud:,} fraud rows ({y_arr.sum() / total_fraud:.1%}). "
        "The rest lack history (fewer than 5 prior rows or fewer than 4 components) and are not scored.", "",
        "## Result", "",
        f"- AUC of the composite against `is_fraud`: **{auc:.3f}** (95% stratified bootstrap [{lo:.3f}, {hi:.3f}], {RESAMPLES:,} resamples, seed {SEED}); 0.5 is a coin.",
        f"- For context, the organizer's `fraud_score` on the same rows that have one: **{fs_auc:.3f}**.",
        f"- **Wording the gates allow:** {verdict(lo, auc)}", "",
        "| Component | AUC | Rows with it | Fraud rows with it |", "|---|---|---|---|",
        *[f"| {c} | {a:.3f} | {n:,} | {f:,} |" for c, (a, n, f) in comp_auc.items()], "",
        "The composite stays descriptive whatever this says: it routes, blocks and answers nothing (ADR-005).", "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
