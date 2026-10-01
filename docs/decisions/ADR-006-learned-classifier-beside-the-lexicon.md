# ADR-006: a learned intent classifier beside the keyword lexicon, not instead of it

- **Status:** accepted, recorded 2026-10-01 (the work it records is from 2026-09-28 to 2026-09-29).
- **Context:** the brief asks for at least one learned component evaluated against a baseline (the fraud labels could not
  supply one: [ADR-005](ADR-005-no-fraud-or-risk-model.md)). Before the model there was a keyword baseline
  (`agent/llm/baseline_classifier.py`) and an escalation lexicon (`agent/policy/signals.py`). Escalating wrongly is the
  expensive mistake, so what the classifier does to the escalation guard matters more than its accuracy.

## How we got here, in order

1. **Keywords first.** Rules written from the training templates alone, then frozen. On the held-out test they get
   63.5% accuracy (macro-F1 0.66), and 25.0% on abbreviated phrases ("q saldo").
2. **Held-out set written after the freeze,** with different phrasing on purpose (regional slang, no accents, ES/PT
   code-switching), split by intent-stratified hash into dev (88) and test (85 once one leaked phrase is left out).
3. **TF-IDF n-grams + logistic regression.** Character n-grams (`char_wb` 2 to 5), word n-grams (1 to 2) or both, with
   class-balanced weights for the small `out_of_scope` and `requires_escalation` classes. No pretrained weights: the
   build environment cannot download embedding models.
4. **Representation chosen without the test split.** Char+word won on dev (macro-F1 0.90 against 0.83 char and 0.82
   word). Later the rule became the mean of dev and a cross-validation on the training set grouped by template, because
   88 phrases are a thin basis for a choice; char+word still wins (0.9008 against 0.8724 for char).
5. **The classifier alone is a worse guard than the lexicon.** On `requires_escalation` in test: lexicon 86.7% recall,
   classifier 46.7%, both together 93.3%, with 0.0% false escalations in each. So the runtime guard is lexicon **or**
   P(requires_escalation) ≥ τ.
6. **τ = 0.55,** chosen on dev only: maximum recall with at most 5% false escalations.
7. **Trace requests were left out of the classes.** Retraining with trace examples fixed "necesito que rastreen un pago
   que no se acreditó" but lost a fraud report ("não reconheço essa compra"). That choice was made after seeing the test
   split and is disclosed as such (LIMITATIONS.md).

## Decision

1. The learned classifier stays, with the keyword baseline as the thing it is compared against, paired on the same 85
   utterances: **84.7% against 63.5%, +21.2 points** (paired bootstrap 95% [+8.2, +34.1], exact McNemar p = 0.0029).
2. It never replaces the lexicon in the guard: the lexicon fires first and the classifier can only add escalations.
3. Its other job is to tell ABSTAIN from CLARIFY when the model answers without a tool, instead of "the reply has a
   question mark".
4. If the model file is missing, both jobs fall back to keywords and the degradation is logged.

## Consequences

- Guard recall on test is 93.3% (14 of 15); the miss, "vou processar o banco", is reported and not added to the lexicon.
- 1 of 12 team-written trace requests reads as a possible dispute and goes to a person: safe, not self-served.
- Slang is the weak spot (33% on 3 phrases), and the same team wrote training and held-out text, so shared phrasing
  habits can inflate both systems. Only a set written by outsiders settles that
  ([`docs/human_set.md`](../human_set.md)).
- Reproduced by `make train-eval`; the report is `eval/reports/intent_classifier.md`.
