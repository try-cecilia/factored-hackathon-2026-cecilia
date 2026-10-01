# Which column each outcome depends on, with a permuted-label control (auto-generated)

`python -m analysis.label_scan` at 2026-10-01T12:35:08+00:00: 240,056 Transaccional contacts (accounts and payments, ADR-003). Gradient boosting, chronological 70/30 split, AUC on the later 30% (0.5 is a coin). The permuted control fits the same model on shuffled training labels, 5 times; its worst AUC is the level of 'no signal' at this size.

| Target | Rows | All columns | Permuted (worst of 5) | Best single column | Next best | Reading |
|---|---|---|---|---|---|---|
| was_resolved | 240,056 | **0.939** | 0.528 | `requires_followup` 0.925 | `duration_seconds` 0.596 | signal, spread over several columns (`requires_followup` alone gets 0.925) |
| was_escalated | 240,056 | **0.499** | 0.507 | `hour` 0.506 | `wait_time_seconds` 0.503 | no signal: indistinguishable from shuffled labels |
| requires_followup | 240,056 | **0.691** | 0.511 | `was_resolved` 0.689 | `duration_seconds` 0.533 | lookup of `was_resolved`: the other columns add nothing |
| csat_low | 44,837 | **0.668** | 0.510 | `was_resolved` 0.667 | `requires_followup` 0.643 | lookup of `was_resolved`: the other columns add nothing |

Targets: `was_resolved` = first-contact resolution, the human baseline the assistant is measured against; `was_escalated` = what the assistant hands to a person; `requires_followup` = the contact did not close; `csat_low` = a dissatisfied customer (CSAT 1-2 of 4), only contacts that got a CSAT survey.
A target's own column and the survey score are left out of its features; the other contact outcomes (`was_resolved`, `was_escalated`, `requires_followup`) are features, which is how a dependence between outcomes (e.g. satisfaction on resolution) shows up as a lookup.
