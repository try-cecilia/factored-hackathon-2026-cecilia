# Calibration of the escalation probability (auto-generated)

`python -m eval.calibration`. The runtime guard escalates when P(requires_escalation) >= tau = 0.55, a value chosen on dev (max recall with false escalations <= 5%). Model, split and tau are the ones `eval.evaluate_intent_classifier` produces; nothing is re-fitted or re-chosen here. Held-out utterances are team-written (LIMITATIONS.md).

## Test split (scored once)

n = 85, 15 escalations. **ECE of P(requires_escalation) = 0.071** (95% bootstrap [0.046, 0.132], 2,000 resamples); Brier 0.076; top-label ECE over all six intents 0.203.

| P(escalation) bin | n | Mean predicted | Observed escalations (Wilson 95%) |
|---|---|---|---|
| [0.00, 0.10) | 46 | 0.04 | 0/46 = 0% [0%-8%] |
| [0.10, 0.30) | 29 | 0.18 | 7/29 = 24% [12%-42%] |
| [0.30, 0.55) | 3 | 0.40 | 1/3 = 33% [6%-79%] |
| [0.55, 0.80) | 5 | 0.64 | 5/5 = 100% [57%-100%] |
| [0.80, 1.00) | 2 | 0.91 | 2/2 = 100% [34%-100%] |

At tau = 0.55 (classifier alone, without the lexicon): precision 7/7 = 100.0% [64.6%-100.0%]; recall 7/15 = 46.7% [24.8%-69.9%]; false escalations 0/70 = 0.0% [0.0%-5.2%].

## Dev + test pooled (more escalations, but dev chose tau, so read it as descriptive)

n = 173, 31 escalations. **ECE of P(requires_escalation) = 0.062** (95% bootstrap [0.052, 0.100], 2,000 resamples); Brier 0.062; top-label ECE over all six intents 0.242.

| P(escalation) bin | n | Mean predicted | Observed escalations (Wilson 95%) |
|---|---|---|---|
| [0.00, 0.10) | 92 | 0.05 | 0/92 = 0% [0%-4%] |
| [0.10, 0.30) | 50 | 0.18 | 8/50 = 16% [8%-29%] |
| [0.30, 0.55) | 12 | 0.37 | 4/12 = 33% [14%-61%] |
| [0.55, 0.80) | 12 | 0.67 | 12/12 = 100% [76%-100%] |
| [0.80, 1.00) | 7 | 0.86 | 7/7 = 100% [65%-100%] |

At tau = 0.55 (classifier alone, without the lexicon): precision 19/19 = 100.0% [83.2%-100.0%]; recall 19/31 = 61.3% [43.8%-76.3%]; false escalations 0/142 = 0.0% [0.0%-2.6%].
