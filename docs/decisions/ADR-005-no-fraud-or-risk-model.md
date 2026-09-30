# ADR-005: no fraud or risk model; the fraud labels are evidence for a person

- **Status:** accepted, recorded 2026-09-29.
- **Context:** the brief asks for at least one learned component evaluated against a baseline, and the dataset carries
  `is_fraud` and `fraud_score` on 4.4 million transactions, so a fraud model is the obvious candidate. Before building
  one we measured whether the labels hold anything a model could learn (`python -m analysis.label_signal`, results in
  [`docs/evidence/label_signal.md`](../evidence/label_signal.md)).

## What we measured

- **`is_fraud` cannot be learned from the transaction.** Gradient boosting on amount, hour, weekday, channel, merchant
  category, country, type and category, trained on the earlier 70% of a chronological sample of every fraud row (4,316 of
  4,425,008 transactions) and scored on the later 30%: AUC **0.506**. Adding the columns that describe what happened
  after the fact (status, response code), which a real-time decision cannot see: **0.508**. That is a coin.
- **`fraud_score` agrees with `is_fraud`** (AUC 0.847, over the 3,539,851 transactions that have a score; it is missing
  on 885,157, of which 891 are fraud). At the threshold the system uses to flag a movement for the reviewer
  (`fraud_score >= 70`), precision is **100%** (999/999). Recall is **29.2%** of the frauds that have a score (999/3,425)
  and **23.1%** of all frauds (999/4,316). A score that is never wrong when it fires and misses most fraud is what a
  score built from the label looks like. We did not verify how the organizer produced it, so we
  do not treat it as a signal independent of the label.

## Decision

1. **No fraud or risk model.** A model trained on a label with no learnable signal would produce a number that means
   nothing, and presenting it as the learned component would be the wrong kind of evidence.
2. **The learned component is the intent classifier** (`eval/reports/intent_classifier.md`), which beats a keyword
   baseline on text it did not see, and whose data, leakage and split checks are in
   [`docs/evidence/data_ml_validation.md`](../evidence/data_ml_validation.md).
3. **The fields are shown to a person, never decided on.** When the customer reports fraud, theft or an account takeover,
   the words of the customer decide the handoff (the lexicon and the classifier guard, `agent/policy/router.py`). The
   handoff ticket then lists the customer's ten most recent movements with the ones flagged by the fields first
   (`agent/policy/escalation.py`, `_evidence_for`), so the reviewer starts where the data points. Nothing is routed,
   blocked or answered because of `is_fraud` or `fraud_score`.

## Trade-offs

- We give up a fraud-detection showcase. The brief does not ask for one, and it does ask that a learned component be
  evaluated against an appropriate baseline, which the intent classifier is.
- If the labels changed (real outcomes instead of synthetic ones), point 1 would be revisited, and `analysis/label_signal.py`
  is the check to rerun first.
- The score's 100% precision means the evidence ordering is reliable on this dataset, not that it would be in a bank.
