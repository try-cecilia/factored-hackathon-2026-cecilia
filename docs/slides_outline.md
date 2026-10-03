# Slide outline (a cover and 5 slides)

Every number is measured: the offline ones come from `eval/reports/SYSTEM_EVAL.md` and
`SYSTEM_EVAL_ADVERSARIAL.md`, the live ones from `eval/reports/SYSTEM_EVAL_LIVE.md` (2026-09-28). If a report is
regenerated, copy the numbers again from it. Speaker notes follow `docs/video_pitch_script.md`.

## 0. Cover
- "Account and payment questions, answered in seconds, only with verified data": balances, movements, payment
  status and exchange rates, in Spanish and Portuguese, for Mexico, Colombia and Argentina.
- For customers of a retail bank who wait in a queue to ask about a balance or a payment: an assistant that only says
  what it can verify, acts once and only on the customer's yes, and hands over to a person, with evidence, when it
  should not act.
- Team [name] · [deployed URL].

## 1. The problem, measured
- Who has it: the customers, and the bank's contact center: about **411 agent hours a month** (median) on these contacts.
- Account and payment questions are **35%** of 686K contacts, the largest reason.
- They are the simplest: **91.5%** resolved on first contact, 221 s calls.
- Yet customers rate it **2.91/5** (NPS −70), and every call starts with **120 s** in the queue.
- Simple, repetitive and already resolvable → automate it, safely.
- *(footnote: the wait is 120 s for every reason in this synthetic data, so we do not claim it drives the score)*
- *(chart: contact reasons; handle time vs CSAT by reason, `docs/evidence/baseline_metrics.md`)*

## 2. The model interprets; the code speaks
- One primary model response per turn chooses the lookup. It never receives a customer record: identifiers the
  customer types are masked, products are aliases, and our replies stay in its history without figures (what the
  customer typed, amounts included, stays as written).
- Every reply comes from verified tool results or a fixed template, so no invented figure can reach a customer.
- Ownership is checked in SQL; fraud, compliance holds and another customer's product are caught before the model.
- **One action**: tracing a pending movement, opened only on the customer's plain yes (judged in code), and
  announced only after it reads back.
- *(diagram: Understand → Decide → Act → Verify → Escalate, with the model's single job highlighted)*

## 3. Proof (held-out cases, ES + PT)

| | Keyword bot (548 cases) | Sonnet 5 (138 of them, run 1 of 3) | Haiku 4.5 (138 of them, run 1 of 3) |
|---|---|---|---|
| Safe automated resolution | 70.2% | **95.0%** | 78.3% |
| Required escalations missed | 72 of 168 | 0 of 42 | 9 of 42 |
| Unsafe outcomes | 0 | **0 in each run** | 1, in one of the 3 runs |
| Cases that sent a record to the model | n/a | 0 | 0 |
| p50 / p95 latency per case | 6.5 / 31.3 ms | 1.9 / 4.2 s | 1.1 / 4.2 s |
| Model cost per safe resolution | no model | USD 0.0034 | USD 0.0079 |
| Cases that changed outcome between runs | deterministic | 0.7% | 2.2% |

- Across the three runs: safe automated resolution 95.0–96.7% on Sonnet 5 and 76.7–78.3% on Haiku 4.5. Haiku 4.5's one
  unsafe outcome (run 2) is a reply outside the templates; Sonnet 5, the deployed model, had none.
- Adversarial model (obeys injections, invents figures): 0 unsafe in 548; automation drops to 60.5%.
- Ideal model, the upper bound on the model's understanding: 99.2%.
- Learned intent classifier on unseen text: 84.7% vs 63.5% for keywords† († post-hoc: two lexicon patterns touched this split; upper bound).
- Groq's gpt-oss-120b not run (no key).

## 4. Data and engineering rigor
- Contracts with a quarantine gate and rollback; lineage per row, run and partition; a late-arrival fixture.
- Findings the data dictionary hides: 57% missing USD amounts; registration branch keys broken for 149,995 of
  150,000 customers; no MXN at all; transcripts with 42 distinct texts; a third of movements dated before their
  product or customer existed; 58K pending movements (the action's ground). Full load: 294 checks, 0 errors.
- Every classifier selection and evaluation run tracked in MLflow: model, effort, prompt hash, data hashes,
  code version and metrics.
- 1,400 hermetic Python tests and about 700 web tests; CI builds the container and boots it like the host; `make all`
  rebuilds every number.

## 5. Try it, and what it takes to make it real
- **Try it:** [deployed URL]. Guided scenarios, "Why?" on every reply, the bank view, fault buttons, and the
  data-quality view (lineage, failed checks and freshness, live from the warehouse).
- **Before production:** the bank's IdP instead of the test PIN; Redis sessions; PII encryption and redaction;
  the metrics stack wired to the specified alerts; voice (85% of contacts are calls).
- **Next workflow:** transaction disputes, on the same spine.
