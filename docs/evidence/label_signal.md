# Signal in the fraud labels (auto-generated)

`python -m analysis.label_signal` at 2026-09-30T08:02:04+00:00 on the full warehouse: 4,425,008 transactions, 4,316 with `is_fraud` (0.098%).

## The organizer's `fraud_score` against `is_fraud`

- The score is missing on 885,157 transactions, 891 of them fraud. Everything below about the score is over the 3,539,851 that have one (3,425 of the 4,316 fraud rows).
- AUC over the rows with a score: **0.847** (0.5 is a coin).
- At the flag threshold the system uses (`fraud_score >= 70`): 999 movements flagged, precision **100.0%** (999/999). Recall is **29.2%** of the frauds that have a score (999/3,425) and **23.1%** of all frauds (999/4,316).

## Can `is_fraud` be learned from the transaction?

Gradient boosting, a chronological 70/30 split of every fraud row and 300,000 sampled legitimate ones, AUC on the later 30%:

| Features | AUC |
|---|---|
| live features | **0.506** |
| live + after the fact | **0.508** |

Live features: amount_usd, hour, weekday, channel, merchant_category, transaction_country, transaction_type, transaction_category. After the fact: transaction_status, response_code.

## What follows

An AUC near 0.5 means the label holds nothing a model could use, and it would be wrong to present any fraud model as a result. A high AUC of the score against the label says the two agree, not that either matches real fraud: both are fields of a synthetic dataset. A precision of 100% at the flag, with most fraud below it, is what a score built from the label looks like; we did not verify how the organizer produced it, so the score is not treated as a signal independent of the label. The system therefore uses the fields as evidence for a person and never as a decision (docs/decisions/ADR-005).
