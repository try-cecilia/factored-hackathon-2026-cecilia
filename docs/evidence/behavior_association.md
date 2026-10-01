# Behavioral composite against `is_fraud` (auto-generated)

`python -m analysis.behavior_association` at 2026-10-01T01:28:14+00:00 on the full warehouse. Protocol and wording gates: [`docs/BEHAVIORAL_EVIDENCE.md`](../BEHAVIORAL_EVIDENCE.md), frozen before this ran. Nothing was fitted.

## Population

- Every one of the 4,233 customers with a fraud transaction, plus 20,000 others (seed 0): 837,912 transactions, 4,316 of them fraud.
- A composite exists for 714,247 of them (85.2%), including 3,620 of the 4,316 fraud rows (83.9%). The rest lack history (fewer than 5 prior rows or fewer than 4 components) and are not scored.

## Result

- AUC of the composite against `is_fraud`: **0.504** (95% stratified bootstrap [0.494, 0.513], 1,000 resamples, seed 0); 0.5 is a coin.
- For context, the organizer's `fraud_score` on the same rows that have one: **0.848**.
- **Wording the gates allow:** No detectable association with the `is_fraud` label.

| Component | AUC | Rows with it | Fraud rows with it |
|---|---|---|---|
| amount | 0.493 | 811,126 | 4,169 |
| channel | 0.504 | 813,679 | 4,186 |
| category | 0.519 | 188,644 | 1,006 |
| country | 0.502 | 813,679 | 4,186 |
| velocity_24h | 0.481 | 14,786 | 62 |
| velocity_30d | 0.494 | 713,248 | 3,618 |

The composite stays descriptive whatever this says: it routes, blocks and answers nothing (ADR-005).
