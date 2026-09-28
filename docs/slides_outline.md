# Slide outline (5 slides)

Numbers in brackets come from `eval/reports/SYSTEM_EVAL_LIVE.md` after `make eval-live` on the organizer's
warehouse; everything else is already measured. Speaker notes follow `docs/video_pitch_script.md`.

## 1. The problem, measured
- Account and payment questions are **35%** of 686K contacts, the largest reason.
- They are the simplest: **91.5%** resolved on first contact, 221 s calls.
- Yet customers wait **120 s** in the queue and rate it **2.91/5** (NPS −70).
- The pain is the wait, not the difficulty → automate it, safely.
- *(chart: contact reasons; handle time vs CSAT by reason, `docs/evidence/baseline_metrics.md`)*

## 2. The model interprets; the code speaks
- One model call per turn chooses the lookup. It never receives a customer record: identifiers the customer
  types are masked, products are aliases, and the history holds no figures.
- Every reply comes from verified tool results or a fixed template, so no invented figure can reach a customer.
- Ownership is checked in SQL; fraud, compliance holds and another customer's product are caught before the model.
- **One action**: tracing a pending movement, opened only on the customer's plain yes (judged in code), and
  announced only after it reads back.
- *(diagram: Understand → Decide → Act → Verify → Escalate, with the model's single job highlighted)*

## 3. Proof (held-out cases, ES + PT, live models, 3 runs each)

| | Keyword bot | Sonnet 5 | Haiku 4.5 | gpt-oss-120b |
|---|---|---|---|---|
| Safe automated resolution | [ ] | [ ] | [ ] | [ ] |
| Unsafe outcomes | [ ] | [ ] | [ ] | [ ] |
| Cases that sent a record to the model | n/a | [ ] | [ ] | [ ] |
| p50 / p95 latency | [ ] | [ ] | [ ] | [ ] |
| Cost per safe resolution | — | [ ] | [ ] | [ ] |
| Cases that changed outcome between runs | — | [ ] | [ ] | [ ] |

- Adversarial model (obeys injections, invents figures): [0 unsafe in N].
- Learned intent classifier on unseen text: 84.9% vs 62.8% for keywords.

## 4. Data and engineering rigor
- Contracts with a quarantine gate and rollback; lineage per row, run and partition; a late-arrival fixture.
- Findings the data dictionary hides: 57% missing USD amounts; registration branch keys broken for 149,995 of
  150,000 customers; no MXN at all; transcripts with 42 distinct texts; 58K pending movements (the action's
  ground).
- Every classifier selection and evaluation run tracked in MLflow: model, effort, prompt hash, data hashes,
  code version and metrics.
- 333 hermetic tests; CI builds the container and boots it like the host; `make all` rebuilds every number.

## 5. Try it, and what it takes to make it real
- **Try it:** [deployed URL]. Guided scenarios, "Why?" on every reply, the bank view, fault buttons, and the
  data-quality view (lineage, failed checks and freshness, live from the warehouse).
- **Before production:** the bank's IdP instead of the test PIN; Redis sessions; PII encryption and redaction;
  the metrics stack wired to the specified alerts; voice (85% of contacts are calls).
- **Next workflow:** transaction disputes, on the same spine.
