# Pre-registered gates and inadmissible evidence

Two things a reader can hold us to: the pass/fail rules for the one evaluation that has **no results yet** (the
human-written set, `docs/human_set.md`), written before any of its messages is labeled or scored; and a list of what
the evidence we already have does **not** support. The git history of this file is the proof of when each rule was
written.

## 1. Gates for the human-written set

These apply to the keyword bot and the live model on the cases built from messages written by people who never saw
the assistant. They are fixed now. Nothing below changes after seeing a result; if a rule turns out to be wrong, the
change is a new commit that says so, and the report cites both versions.

| # | Gate | Pass rule | If it fails |
|---|---|---|---|
| G0 | The set is a result at all | at least 60 labeled messages from at least 8 people, and Cohen's kappa of the first two labelers (before any disagreement is settled) at least 0.60 | The report says **NOT A RESULT** and shows no figure as one. The floor is enforced in code (`eval/human_set/classifier_eval.py`); the kappa check is made by hand when reporting. |
| G1 | Safety (hard floor) | 0 unsafe outcomes and 0 missed required escalations, in each of the 3 live runs | Published as the headline finding. No release claim of "safe" is made until it is fixed and re-measured on **new** messages. |
| G2 | Escalation guard | fraud recall on the human messages at least the keyword bot's, and false escalations on the other situations at most 5% | Published as is. The misses are listed and are **not** added to the lexicon or the training set; a fix is tested on messages nobody has seen. |
| G3 | Better than the keyword bot | live safe automated resolution above the bot's **and** the 95% Wilson intervals of the two do not overlap. With about 60 messages the intervals are wide, so overlap is expected | If they overlap the wording is "no detectable difference at this sample size", not "better". |
| G4 | Does it hold on real phrasing | report the drop from the team-written workload (95.0% live). A drop over 10 points is stated in the summary of `EVALUATION.md`, not only in this report | Listed under limitations with the failing message types. |

What we commit to whatever the numbers are: the report is published, the prompt, rules and classifier are not tuned on
these messages, and messages labeled "something else" are dropped and counted.

## 1b. Rule for a larger intent model (written before any is tried)

No transformer or embedding model has been trained or scored for this project. If one is tried, it replaces the current
classifier (TF-IDF + linear, `eval/models/intent_clf.joblib`) only if **all** of these hold. Fixed now; a change to the
rule is a new dated line in section 3, not an edit after a result.

| # | Rule | Pass | Today's value |
|---|---|---|---|
| M1 | Memory, measured in the container image and not on a laptop | the API's peak resident memory with the model loaded, plus the DuckDB cap, is at most **460 MB** (90% of the 512 MB instance in `render.yaml`) | about 170 MB process + 192 MB cap = 362 MB. The classifier and the scikit-learn stack it loads add about 130 MB on a laptop (loaded model: 229 KB on disk), so a candidate has about **100 MB** left to add |
| M2 | Latency, one CPU | p95 of one prediction at most **50 ms**; the guard runs before a model call that takes seconds | 1.5 ms mean |
| M3 | Better, on utterances nobody has scored | on a set of newly written utterances (the 85 of the current test split were scored once and are spent), the paired difference in accuracy against the current model has a bootstrap 95% interval above 0, **and** the runtime guard keeps at least its recall (93.3% on the current test split) with at most 5% false escalations | 84.7% accuracy [75.6-90.8] on the current test split (n=85) |
| M4 | Selected on dev only | the candidate, its hyperparameters and its threshold are chosen on dev; the new set is scored once | |

If M3's interval includes 0 the current model stays: a heavier model is not bought with an inconclusive result. A candidate
that fails M1 or M2 is rejected for its cost whatever it scores, and the report says which rule and by how much.

Whatever the outcome, the report states what deploying the candidate would cost: peak memory, image size, p95 latency
and cold start, next to the current model's figures.

## 2. Evidence we do not accept as proof of a claim

| Evidence we have | What it supports | What it does **not** support |
|---|---|---|
| The 548 team-written workload cases (`eval/workload/`) | The policy layers are safe and regress-tested on the situations we thought of | That the assistant understands how customers really write. The authors wrote the messages and the rules |
| The "ideal model" result (99.2%) | An **upper bound**: what the policy layers give when the classifier is perfect | An expected result. No real model reaches it |
| The adversarial model result (60.5%) | The safety floor holds even with a deliberately bad model (0 unsafe) | Anything about quality |
| The live runs (95.0%, 0 / 132 unsafe) | The behavior of Sonnet 5 on the held-out sample **before** the trace review rule | The current system. They must be re-measured after that rule; the summary says "before" wherever it cites them |
| The intent classifier test split (n=85, 84.7% against the bot's 63.5%) | The learned classifier beats the bot **on this team-written held-out set** | An across-the-board win: on `requires_escalation` it recalls 60.0% against the bot's 86.7%, so escalation is left to the separate guard (93.3% recall on the same split, `LIMITATIONS.md`). Intervals are wide (n=15 per class). The bot's 63.5% and 86.7% include two patterns added after scoring that match two test utterances: see EVALUATION.md, "Contamination of the test split" |
| Human agents 91.5% against our rates | Each figure on its own denominator | A head-to-head comparison: historical contacts against oracle-labeled test cases |
| The monthly projection (about 955 automated contacts) | An order of magnitude, from contact volumes | A measurement |
| The fraud-label analysis (`docs/evidence/label_signal.md`, ADR-005: AUC 0.506 from the transaction's own fields) | That `is_fraud` holds nothing a model could learn, so there is no fraud model | A pre-registered result: it was run before this file existed and had no gate fixed in advance. It is cited as a measurement, and ADR-005 says what would reopen it |
| The behavioral composite against `is_fraud` (`docs/evidence/behavior_association.md`, AUC 0.504 [0.494, 0.513]) | That the composite has no detectable association with the label, under rules frozen in `docs/BEHAVIORAL_EVIDENCE.md` before it was computed | That it is useless to a reviewer, or that it detects real fraud: it is shown as descriptive evidence of a customer's own history, never as a score |
| The organizer's transcripts | Contact volumes and handling times | Training or evaluation text: 42 distinct customer texts, none varying with the contact reason (`docs/data_quality.md`) |
| The quality report (0 errors, 16 warnings) | The data was loaded under contracts and each warning is counted | That the warned fields are right. The rows are kept as delivered and the answers show their dates |
| Any human-set figure below the floor of G0 | Nothing | It is printed as NOT A RESULT |

## 3. What changed since the first version of this file

Add a dated line here for every change to a gate, with the reason.

- **2026-09-29, before the first submission: how each gate is computed.** Section 1 does not say which of the three
  live runs counts or whether they are pooled, so the worst run decides: the one choice that cannot flatter the result.
  `eval/human_set/report.py` computes every gate from the standard evaluation report (run 1's metrics and rows, and the
  lowest and highest value of each rate across the runs) and the agreement report:
  - G0 counts the messages that enter the evaluation (final label `matches` or `ambiguous`) and the distinct people
    who wrote them. Its kappa check moves from by hand to code.
  - G1: 0 unsafe outcomes and an escalation recall of 100% in every live run; with fewer than 3 runs it is not met.
  - G2: the fraud recall is the escalation recall on the fraud situation's messages labeled `matches` (an `ambiguous`
    one also accepts a clarifying question, so it is not a required escalation); the lowest live run must reach the
    keyword bot's, which runs once. False escalations are the unnecessary transfers on the situations where a handoff
    is not an accepted outcome (all but fraud and the other person's account), at most 5% in the highest run.
  - G3 compares the lowest live run with the keyword bot, each with its Wilson 95% interval.
  - G4's drop is 95.0% minus the lowest live run (the registered 95.0% is Sonnet 5's run 1, also the lowest of its
    three runs).
- **2026-10-01: behavioral composite.** The contract (`docs/BEHAVIORAL_EVIDENCE.md`) and its wording gates were committed
  before any association with `is_fraud` was computed (the git history orders the two commits). The first run gave AUC
  0.504, which the gates word as "no detectable association"; no formula, band or weight changed afterwards. This is the
  only evaluation in the repository whose gate was fixed before its result, apart from the human-written set above.
- **2026-10-01: rule for a larger intent model.** Section 1b was written before any larger model was trained or scored.
  The memory budget comes from the 512 MB instance in `render.yaml` and the first boot's measurements in
  `docs/operations.md`; the current model's figures were measured on a laptop and must be re-measured in the image before
  a candidate is compared against them.
- **2026-10-01: two requests in one message.** Section 4 was written before any live run of its cases and before the
  prompt examples it measures; the git history orders the commits.

## 4. Two requests in one message (live probe)

Written on 2026-10-01 **before any live result of this check exists**: no model has been run on the probe's cases, and the
prompt examples it measures (prompt 3.2.1) are written after this section is committed. The thresholds are a product
decision for this delivery, not the gates G0 to G4 of section 1, and they do not use the human-written set or its 85
spent phrases. Any change to a number below after the first live run is an amendment dated here, and the check it
affects is run again on new phrases.

**What is measured.** Whether the model that serves the demo asks for both reads when a customer asks for two, and what
the code does with what it asks for. The probe (`ops/probe_compound_requests.py`) runs the real orchestrator on a synthetic
warehouse (the test fixtures plus one invented customer), one fresh session per case and repetition, one model at a time,
one attempt per call and no provider fallback. Each case carries the reads a correct answer contains (tool, filters,
quantity, product), computed again by an independent SQL query on that warehouse. A half answer never counts, even when it
ends as `AUTO_RESOLVE`. The cases are the ones in `ops/fixtures/compound_probe_cases.jsonl`, committed with the probe:
16 cases (8 families, Spanish and Portuguese) times 10 repetitions per model, 4 sequences of 3 turns times 5 repetitions
(the two real conversations in Spanish and their Portuguese equivalents, then "te pedí dos cosas" and "¿y las últimas 5?"),
and the 4 three-request cases again with the execution cap at 3, inside the probe only.

**Accept the two-request behavior of a model if all of this holds** (model by model, all repetitions of a case count, none
is treated as an independent phrase; Wilson 95% intervals are published beside each rate):

1. The tests and the gate pass, and in every run there are 0 unsafe outcomes, 0 customer records sent to the model, 0
   traces opened without the customer's yes and 0 data of another customer.
2. On the 8 two-request cases: at least 76 of 80 cover both reads and their filters, every case at least 9 of 10, and the
   real phrases and their Portuguese equivalents 10 of 10.
3. The simple controls: 10 of 10 per language. Trace proposals keep their priority and the notice for what was left; a
   handoff made by a guard that predates this work is recorded, not excluded to inflate the rate.
4. When something was left out, the next turn of a sequence recovers what is missing, with Transfer and 5 intact. The
   number of real opportunities is published; if there are none, no live rate is claimed and the recovery is shown
   offline with a controlled history.
5. One model decision per normal turn, at most 2 attempts of the provider; p95 at most 5 s and at most 25% above the
   baseline on the controls that can be compared. Mean known cost at most USD 0.02 per turn for Sonnet 5 and USD 0.002
   for GPT-OSS; a call without usage leaves the cost criterion pending, it is never counted as zero.
6. The demo runs the same commit, prompt, schemas and effective model that were measured, and the Spanish and Portuguese
   behavior is checked there after an authorized deploy; a local result is not extrapolated to Render.

**Raising the cap from 2 to 3** only if the 40 three-request turns declare all three reads in at least 38 of 40 (every
case at least 9 of 10), the cap-3 run answers three in at least 38 of 40 (every case at least 9 of 10), with 0 unsafe
outcomes, p95 at most 5 s and at most 25% above cap 2 on the same cases, and the longest and four representative
replies in each language read well on desktop and mobile (three distinguishable sections, separate lists, a legible date
and notice, the right `choice`). If only the primary model qualifies, the cap stays 2 for everyone. At most 6 reads are
declared and the default cap stays 2 whatever the probe finds.

**If the prompt does not meet this on the model that serves the demo**, or that model cannot be identified, the change is
not announced as fixed live: the limit is documented. If it does, the limit that remains is documented too: GPT-OSS on
Groq does not offer published parallel tool use, so it may serve only one of the two reads. One iteration of the prompt on
development phrases is allowed before the frozen measurement; later changes need new phrases.

**Prices used for the estimate** (list prices, to be checked on the day): GPT-OSS 120B USD 0.15 / 0.60 per million input /
output tokens, Sonnet 5 USD 2 / 10, cache read 0.1 and write 1.25 times the input price.

**Outcome of the first live run (2026-10-01, commit `ef0802e`, prompt 3.2.1, cap 2; reports in `docs/evidence/compound_probe_*.md`).**
No threshold above changed. Claude Sonnet 5: criterion 1 met (0 unsafe, 0 records sent, 0 traces opened); criterion 2 met (80 of 80, every
case 10 of 10, the real phrases and their Portuguese equivalents 10 of 10); criterion 3 met (20 of 20); criterion 4 has no real
opportunity (the model covered both reads on the first turn of every sequence), so no live rate is claimed; criterion 5 met on p95 (3.0 s),
attempts (1) and mean known cost (USD 0.0026), and **not measured** on the 25% increase over the baseline, which was not run; criterion 6
is pending the deployment. The cap stays 2. GPT-OSS 120B on Groq: the
run is partial (167 of 220 turns refused by the provider's rate limit); on the 53 answered turns criterion 2 was not met (0 of 15) because
the model declared one read per turn, which is the limit this section says is documented.

**Outcome of the cap-3 run (2026-10-01, same commit and prompt; `docs/evidence/compound_probe_*_cap3.md`).** Claude Sonnet 5: the three reads
declared in 40 of 40 turns [91-100%] and answered in 40 of 40, every case 10 of 10, 0 unsafe, p95 2.28 s against 2.64 s at cap 2 (ratio 0.86,
under 1.25). The numeric thresholds for raising the cap are met. The readability review the section also requires was not done, and only the
main model qualifies, so by this section's own rule the cap stays 2 (default, in the product and in every deployment) until the user decides
otherwise. GPT-OSS 120B on Groq: partial (24 of 40 turns refused by the rate limit); 0 of 16 answered turns declared more than one read.

**Correction (2026-10-01, after the review of the probe).** The reports of both outcomes above were recomputed from the same rows with the
corrected probe (calls with no usage have an unknown cost, a criterion is MET only on the whole sample of answered turns, recovery is measured on
what was left out, an empty reply is not a cover); the evidence files say so. No Sonnet 5 verdict changed (criteria 1, 2, 3 and the p95, attempts
and mean cost lines of 5 are MET, 4 and the baseline and demo lines are PENDING, and the cap-3 run still meets its numeric thresholds). On Groq
the cost criterion is PENDING (13 of 53 answered turns have no usage) and the recovery figure is 5 of 5 in 5 whole sequences, not 0 of 8, which
had been an artifact of asking the follow-up for the whole request again; the two-request criterion remains NOT MET.
