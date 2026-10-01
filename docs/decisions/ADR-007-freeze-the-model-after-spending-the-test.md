# ADR-007: the model is frozen once the test split has been spent

- **Status:** accepted, recorded 2026-10-01.
- **Context:** the classifier's test split is 85 utterances, scored once (EVALUATION.md). A score on it only means
  something if nothing chosen afterwards was chosen by looking at it, and there is more to measure later: the
  human-written set (`docs/human_set.md`) exists to say how the assistant reads people who never saw it.

## What has already touched the test split

Recorded so the rule below is read against what happened, not against an ideal:

- The patterns `no fui yo` / `yo no fui` / `não fui eu` / `eu não fui` were added to the lexicon after the held-out set
  was scored, and two test utterances contain them. Lexicon-only recall went from 80.0% to 86.7% and the paired
  difference from +22.4 to +21.2 points. They came from another team's public repository, not from those utterances,
  but the lexicon and keyword figures are an upper bound. The learned model and the combined guard (93.3%) did not move.
- Retraining with trace examples was rejected after seeing that it lost a fraud report on test (ADR-006).

## Decision

1. **After the test split is scored, the representation, the threshold and the model file do not change to fix what test
   showed.** What it showed (the missed "vou processar o banco", the trace request read as a dispute) is reported and
   stays open.
2. **Nothing is tuned on test.** The representation is chosen on dev and on a cross-validation of the training set; τ on
   dev. A test checks that changing the test labels moves none of the choices
   (`tests/test_data_ml_validation.py`).
3. **A frozen model is a checkable thing.** `intent_clf_meta.json` carries the hash of the training data it was trained
   on; `eval/human_set/classifier_eval.py` refuses to score if that hash no longer matches, since a model that saw the
   messages proves nothing. The model and its metadata are inputs of the evaluation fingerprint, so changing them shows
   up as a changed system, not as the same one.
4. **The human set scores the frozen model** and lists the guard's misses without fixing them; below 60 messages or 8
   people it says NOT A RESULT.
5. **Changing the model is allowed, as a new experiment:** retrain, re-run the whole evaluation, and score on data that
   was not used to decide (a new held-out set, or the human set), with the change recorded in a new ADR.

## Consequences

- Known weaknesses stay visible in the numbers instead of being patched until the score looks good.
- A real improvement (for example trace examples without losing the fraud report) waits for a set that can judge it
  honestly, and costs a retrain and a full re-evaluation.
- The rule covers the model and the lexicon alike; the lexicon contamination above is the one place it was already
  bent, and it is disclosed where the number appears.
