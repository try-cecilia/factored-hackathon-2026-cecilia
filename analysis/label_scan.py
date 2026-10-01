"""Which column carries each outcome of an accounts-and-payments contact, and is it more than chance?

    python -m analysis.label_scan     # reads DUCKDB_PATH (the full_all warehouse), writes docs/evidence/label_scan.md

Population: the Transaccional contacts (ADR-003), the workflow the assistant serves. For each outcome (a "target") three numbers,
on a chronological 70/30 split so the model never sees a contact later than the ones it is scored on:

1. **All columns:** gradient boosting on every other column, AUC on the later 30%.
2. **Permuted control:** the same model fitted on the training labels shuffled. It cannot know anything, so its AUC is what "no signal"
   looks like at this size; a result is only a finding if it clears it. Repeated PERMUTATIONS times, the worst one is reported.
3. **One column:** the same model fitted on a single column, for each column. If the best single column matches the full model, the
   target is a lookup of that column and the other columns are noise (the "lookup of one column" check).

Like analysis/label_signal.py, this reads fields of a synthetic dataset: it says what the labels depend on, not what is true of customers.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT = Path("docs/evidence/label_scan.md")
PERMUTATIONS = 5
SEED = 7
TARGETS = {  # name -> (SQL expression over the joined frame, why it matters for the workflow)
    "was_resolved": ("was_resolved", "first-contact resolution, the human baseline the assistant is measured against"),
    "was_escalated": ("was_escalated", "what the assistant hands to a person"),
    "requires_followup": ("requires_followup", "the contact did not close"),
    "csat_low": ("main_score <= 2", "a dissatisfied customer (CSAT 1-2 of 4), only contacts that got a CSAT survey"),
}
SQL = """SELECT c.interaction_date, c.interaction_type, c.channel, c.contact_reason, c.duration_seconds, c.wait_time_seconds,
                c.detected_sentiment, c.sentiment_score::DOUBLE AS sentiment_score, c.customer_detected_accent, c.agent_used_accent,
                c.has_transcript, c.has_recording, hour(c.interaction_date) AS hour, dayofweek(c.interaction_date) AS weekday,
                u.segment, u.country, c.was_resolved, c.was_escalated, c.requires_followup, s.main_score
         FROM call_center_interactions c JOIN customers u USING (customer_id)
         LEFT JOIN satisfaction_surveys s ON s.interaction_id = c.interaction_id AND s.survey_type = 'CSAT'
         WHERE c.reason_category = 'Transaccional' ORDER BY c.interaction_date"""


def _auc(X: pd.DataFrame, y_train: np.ndarray, y_test: np.ndarray, cut: int) -> float:
    X = X.copy()
    for c in X.select_dtypes(exclude="number"):
        X[c] = X[c].astype("category")
    model = HistGradientBoostingClassifier(random_state=SEED, categorical_features="from_dtype", max_iter=100)
    model.fit(X.iloc[:cut], y_train)
    return roc_auc_score(y_test, model.predict_proba(X.iloc[cut:])[:, 1])


def scan(df: pd.DataFrame, y: pd.Series, features: list[str]) -> dict:
    """df is in chronological order. Returns the three numbers above; the chance level is `permuted_max`."""
    y = y.to_numpy().astype(bool)
    cut = int(len(df) * 0.7)
    rng = np.random.default_rng(SEED)
    return {
        "all": _auc(df[features], y[:cut], y[cut:], cut),
        "permuted_max": max(_auc(df[features], rng.permutation(y[:cut]), y[cut:], cut) for _ in range(PERMUTATIONS)),
        "one": sorted(((_auc(df[[f]], y[:cut], y[cut:], cut), f) for f in features), reverse=True),
    }


def main() -> None:
    con = duckdb.connect(os.environ.get("DUCKDB_PATH", "data/warehouse/full_all.duckdb"), read_only=True)
    df = con.execute(SQL).fetchdf()
    lines = ["# Which column each outcome depends on, with a permuted-label control (auto-generated)", "",
             f"`python -m analysis.label_scan` at {datetime.now(timezone.utc).isoformat(timespec='seconds')}: {len(df):,} Transaccional contacts "
             f"(accounts and payments, ADR-003). Gradient boosting, chronological 70/30 split, AUC on the later 30% (0.5 is a coin). "
             f"The permuted control fits the same model on shuffled training labels, {PERMUTATIONS} times; its worst AUC is the level of 'no signal' at this size.", "",
             "| Target | Rows | All columns | Permuted (worst of "f"{PERMUTATIONS}) | Best single column | Next best | Reading |", "|---|---|---|---|---|---|---|"]
    for name, (expr, _why) in TARGETS.items():
        d = df.assign(csat_low=df["main_score"] <= 2)
        if name == "csat_low":
            d = d[d["main_score"].notna()].reset_index(drop=True)
        else:
            d = d.reset_index(drop=True)
        features = [c for c in d.columns if c not in {name, "csat_low", "main_score", "interaction_date"}]
        r = scan(d, d[name], features)
        (a1, f1), (a2, f2) = r["one"][0], r["one"][1]
        if r["all"] <= r["permuted_max"] + 0.01:
            reading = "no signal: indistinguishable from shuffled labels"
        elif a1 >= r["all"] - 0.01:
            reading = f"lookup of `{f1}`: the other columns add nothing"
        else:
            reading = f"signal, spread over several columns (`{f1}` alone gets {a1:.3f})"
        lines.append(f"| {name} | {len(d):,} | **{r['all']:.3f}** | {r['permuted_max']:.3f} | `{f1}` {a1:.3f} | `{f2}` {a2:.3f} | {reading} |")
    lines += ["", "Targets: " + "; ".join(f"`{k}` = {v[1]}" for k, v in TARGETS.items()) + ".",
              "A target's own column and the survey score are left out of its features; the other contact outcomes (`was_resolved`, `was_escalated`, "
              "`requires_followup`) are features, which is how a dependence between outcomes (e.g. satisfaction on resolution) shows up as a lookup.", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
