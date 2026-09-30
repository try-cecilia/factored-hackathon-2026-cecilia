"""Is there signal in the fraud labels? Two measurements, so a claim about them is a number and not an impression.

    python -m analysis.label_signal          # reads DUCKDB_PATH (the full warehouse), writes docs/evidence/label_signal.md

1. The organizer's `fraud_score` against `is_fraud`, over every transaction: AUC, and precision and recall at the
   threshold the system uses to flag a movement for the human reviewer (`agent/policy/escalation.py`, FRAUD_SCORE_FLAG).
2. Whether `is_fraud` can be *learned* from what a transaction says about itself (amount, hour, channel, category,
   country, type), with a chronological split: train on the earlier movements, score the later ones. Every fraud row is
   kept and the legitimate ones are sampled (an AUC does not change with the sampling of negatives). A second model adds the
   columns that describe what happened after the fact (status, response code), which a real-time decision cannot see.

The system never decides on these labels (docs/decisions/ADR-005): they are shown to the reviewer as evidence.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from agent.policy.escalation import FRAUD_SCORE_FLAG

OUT = Path("docs/evidence/label_signal.md")
LIVE = ["amount_usd", "hour", "weekday", "channel", "merchant_category", "transaction_country", "transaction_type", "transaction_category"]
AFTER_THE_FACT = ["transaction_status", "response_code"]
NEGATIVES = 300_000
SEED = 7


def main() -> None:
    con = duckdb.connect(os.environ.get("DUCKDB_PATH", "data/warehouse/full.duckdb"), read_only=True)
    n, frauds = con.execute("SELECT count(*), count(*) FILTER (WHERE is_fraud) FROM transactions").fetchone()
    s = con.execute("SELECT fraud_score, is_fraud FROM transactions WHERE fraud_score IS NOT NULL").fetchnumpy()
    score, y = s["fraud_score"].astype(float), s["is_fraud"].astype(bool)
    auc_score = roc_auc_score(y, score)
    flagged = score >= FRAUD_SCORE_FLAG
    hits, scored, scored_frauds = int((y & flagged).sum()), len(y), int(y.sum())  # fraud rows without a score cannot be flagged by it
    precision = hits / max(int(flagged.sum()), 1)

    cols = ", ".join(c for c in LIVE if c not in ("hour", "weekday")) + ", " + ", ".join(AFTER_THE_FACT)
    df = con.execute(f"""WITH picked AS (
                             SELECT * FROM transactions WHERE is_fraud
                             UNION ALL
                             SELECT * FROM (SELECT * FROM transactions WHERE NOT is_fraud) USING SAMPLE reservoir({NEGATIVES} ROWS) REPEATABLE ({SEED}))
                         SELECT transaction_date, is_fraud, {cols}, hour(transaction_date) AS hour, dayofweek(transaction_date) AS weekday
                         FROM picked""").fetchdf().sort_values("transaction_date", ignore_index=True)
    cut = int(len(df) * 0.7)  # chronological: the model never sees a movement later than the ones it is scored on
    aucs = {}
    for name, feats in (("live features", LIVE), ("live + after the fact", LIVE + AFTER_THE_FACT)):
        X = df[feats].copy()
        for c in X.select_dtypes(exclude="number"):
            X[c] = X[c].astype("category")
        model = HistGradientBoostingClassifier(random_state=SEED, categorical_features="from_dtype", max_iter=200)
        model.fit(X.iloc[:cut], df["is_fraud"].iloc[:cut])
        aucs[name] = roc_auc_score(df["is_fraud"].iloc[cut:], model.predict_proba(X.iloc[cut:])[:, 1])

    lines = [
        "# Signal in the fraud labels (auto-generated)", "",
        f"`python -m analysis.label_signal` at {datetime.now(timezone.utc).isoformat(timespec='seconds')} on the full warehouse: "
        f"{n:,} transactions, {frauds:,} with `is_fraud` ({frauds / n:.3%}).", "",
        "## The organizer's `fraud_score` against `is_fraud`", "",
        f"- The score is missing on {n - scored:,} transactions, {frauds - scored_frauds:,} of them fraud. Everything below about the score is over the "
        f"{scored:,} that have one ({scored_frauds:,} of the {frauds:,} fraud rows).",
        f"- AUC over the rows with a score: **{auc_score:.3f}** (0.5 is a coin).",
        f"- At the flag threshold the system uses (`fraud_score >= {FRAUD_SCORE_FLAG}`): {int(flagged.sum()):,} movements flagged, precision "
        f"**{precision:.1%}** ({hits:,}/{int(flagged.sum()):,}). Recall is **{hits / scored_frauds:.1%}** of the frauds that have a score "
        f"({hits:,}/{scored_frauds:,}) and **{hits / frauds:.1%}** of all frauds ({hits:,}/{frauds:,}).", "",
        "## Can `is_fraud` be learned from the transaction?", "",
        f"Gradient boosting, a chronological 70/30 split of every fraud row and {NEGATIVES:,} sampled legitimate ones, AUC on the later 30%:", "",
        "| Features | AUC |", "|---|---|",
        *[f"| {k} | **{v:.3f}** |" for k, v in aucs.items()], "",
        "Live features: " + ", ".join(LIVE) + ". After the fact: " + ", ".join(AFTER_THE_FACT) + ".", "",
        "## What follows", "",
        "An AUC near 0.5 means the label holds nothing a model could use, and it would be wrong to present any fraud model as a result. "
        "A high AUC of the score against the label says the two agree, not that either matches real fraud: both are fields of a synthetic dataset. "
        "A precision of 100% at the flag, with most fraud below it, is what a score built from the label looks like; we did not verify how the "
        "organizer produced it, so the score is not treated as a signal independent of the label. "
        "The system therefore uses the fields as evidence for a person and never as a decision (docs/decisions/ADR-005).", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
