# Signal in the fraud labels (auto-generated)

`python -m analysis.label_signal` at 2026-09-29T23:02:24+00:00 on the full warehouse: 4,425,008 transactions, 4,316 with `is_fraud` (0.098%).

## The organizer's `fraud_score` against `is_fraud`

- AUC: **0.847** (0.5 is a coin).
- At the flag threshold the system uses (`fraud_score >= 70`): precision **100.0%**, recall **29.2%** (999 movements flagged).

## Can `is_fraud` be learned from the transaction?

Gradient boosting, a chronological 70/30 split of every fraud row and 300,000 sampled legitimate ones, AUC on the later 30%:

| Features | AUC |
|---|---|
| live features | **0.506** |
| live + after the fact | **0.508** |

Live features: amount_usd, hour, weekday, channel, merchant_category, transaction_country, transaction_type, transaction_category. After the fact: transaction_status, response_code.

## What follows

An AUC near 0.5 means the label holds nothing a model could use, and it would be wrong to present any fraud model as a result. A high AUC of the score against the label says the two agree, not that either matches real fraud: both are fields of a synthetic dataset. A precision of 100% at the flag, with most fraud below it, is what a score built from the label looks like; we did not verify how the organizer produced it, so the score is not treated as a signal independent of the label. The system therefore uses the fields as evidence for a person and never as a decision (docs/decisions/ADR-005).
