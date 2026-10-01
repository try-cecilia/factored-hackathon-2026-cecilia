# Behavioral evidence for the operator: frozen contract

Status: **frozen before any association with `is_fraud` was computed.** The git history of this file is the proof of
when each rule was written. A later change is a new commit with a dated line in section 7 saying why.

Method and component definitions follow the public behavioral-unusualness contract of another entry to this
hackathon (`SplitzHappen/factored-hackathon-2026-proof-of-one`, `docs/BEHAVIORAL_UNUSUALNESS.md`). The adaptations to our
data are in section 3; the evaluation rules and the wording gates in sections 5 and 6 are ours.

## 1. Why this exists

ADR-005 records that `is_fraud` cannot be learned from a transaction (AUC 0.506, `docs/evidence/label_signal.md`), so
there is no fraud model and no risk score. When a customer reports fraud, the handoff ticket lists the ten most recent
movements. This contract adds, to each of them, how far it is from **that customer's own earlier behavior**, so the
reviewer starts where the history looks different. It describes; it does not decide.

## 2. What it is not

Descriptive behavioral evidence only; not a fraud probability or fraud determination. It is not a risk score, a queue
priority, an escalation trigger, or a reason to block, answer or route anything. The handoff is still decided by the
customer's words (lexicon and classifier guard). No code path may read the composite except the ticket's evidence list
and the operator screen that renders it.

## 3. Inputs and the six components

Inputs: the customer's own transactions strictly **before** the one being described (`transaction_date` earlier; rows
with the same timestamp are not prior). Nothing else enters: no `is_fraud`, no `fraud_score`, no status, no future rows,
no other customers. A prior row counts whatever its status (Pending, Declined and Approved are all behavior).

Amounts use `abs(amount)` in the transaction's own `currency`. `amount_usd` is null in 57.3% of rows and is not used
(`docs/data_quality.md`).

| # | Component | Score in [0, 1] | Unavailable when |
|---|---|---|---|
| 1 | Amount surprise | `min(abs(log2(amount / prior_mean_same_currency)) / 2, 1)`: 1x = 0; 2x or 0.5x = 0.5; 4x or 0.25x = 1 | no prior row in that currency, or its mean is 0 |
| 2 | Channel novelty | 1 if the channel was never seen before, else 0 | no prior rows |
| 3 | Merchant-category novelty | 1 if never seen before, else 0 | no prior rows, or the transaction has no category |
| 4 | Country novelty | 1 if `transaction_country` was never seen before, else 0 | no prior rows |
| 5 | 24-hour velocity | `r = prior_24h / (prior_30d / 30)`; `0` if `r <= 1`, else `min(log2(r) / log2(8), 1)` | fewer than 5 prior rows in the 30 days before |
| 6 | 30-day velocity | `r = prior_30d / (prior_lifetime / tenure_days * 30)`; `0` if `r <= 1`, else `min(log2(r) / log2(4), 1)` | fewer than 5 prior rows, or `tenure_days < 60` |

`prior_24h` and `prior_30d` count prior rows in the 24 hours and 30 days before the transaction. `tenure_days` is the days
from the customer's **first prior transaction** to this one, not from `registration_date` or product opening: 18.7% of
movements are dated before their customer registered and 18.7% before their product opened (`docs/data_quality.md`),
and a baseline built on those dates would inherit the contradiction. Velocity measures elevated activity only; a quiet
period scores 0.

## 4. Composite and bands

`composite = 100 * unweighted mean of the available component scores`. No learned weights, no tuning.

Shown only if the customer has at least **5 prior transactions** and at least **4 of the 6** components are available.
Otherwise the composite is unavailable, the available component facts are still listed, and the screen says there is
not enough history. This stops a new customer looking maximally unusual because everything is first-seen.

Bands are labels only: `< 25` low, `25 to < 50` moderate, `50 to < 75` elevated, `>= 75` high observed deviation. They are
not thresholds and nothing may branch on them.

## 5. Evaluation protocol (association report)

One report, `python -m analysis.behavior_association`, writes `docs/evidence/behavior_association.md`:

- Population: every customer with at least one `is_fraud` transaction, plus a seeded random sample of 20,000 other
  customers (seed 0); every transaction of each, scored from its own prior history.
- Only transactions with an available composite are scored. The report counts the rest and says how many of the fraud
  rows are lost that way.
- Metric: AUC of the composite against `is_fraud`, with a 95% bootstrap interval (1,000 resamples, seed 0). For context
  it also prints the AUC of each component and of `fraud_score` on the same rows.
- Nothing is fitted, so no split is needed: the formulas were fixed in section 3 before this ran. The report must not be
  used to change them.

## 6. Pre-registered wording gates

Fixed now. They decide only what we are allowed to **say**; none changes what the screen shows.

| Result | We may say | We must say |
|---|---|---|
| Lower bound of the AUC interval `<= 0.55` | nothing about association | "No detectable association with the `is_fraud` label." Also in the screen's help text if any claim about usefulness is made |
| Lower bound `> 0.55` and point estimate `< 0.65` | "weak association with a synthetic label" | that this is not validation against real fraud |
| Lower bound `>= 0.60` | "association with a synthetic label" | the same, plus the comparison with `fraud_score` |

In every case the report is published, the composite stays descriptive, and the formulas, bands and weights are not
changed after seeing the result. A miss is not repaired by retuning.

## 7. Changes since the first version

Add a dated line for every change, with the reason.

- (none yet)
