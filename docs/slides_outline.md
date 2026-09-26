# Slide outline (6 slides)

## 1. The problem, measured
- Account/payment questions are **35%** of 686K contacts, the largest reason.
- They are the simplest: **91.5%** resolved on first contact, 221 s calls.
- Yet customers wait **120 s** in the queue and rate it **2.91/5** (NPS −70).
- The pain is the wait, not the difficulty → automate it.
- *(chart: contact reasons; AHT vs CSAT by reason — `docs/evidence/baseline_metrics.md`)*

## 2. What we built
- An ES/PT agent for balances, movements, arrears status and FX, answering only from verified data.
- It clarifies ambiguity (which of your two savings accounts?).
- It abstains on out-of-scope requests (card blocking, loans).
- It transfers fraud, compliance holds and missing data to a human with an evidence-rich ticket.
- *(diagram: Understand → Decide → Act → Verify → Escalate)*

## 3. The model proposes, the code disposes
- The LLM never sees or sets whose account; ownership is checked in SQL.
- Every figure in an answer must appear in a tool result, or the answer is re-rendered from the facts.
- Policy rules run before the model: fraud lexicon + learned classifier (93% recall, 0 false alarms).
- **Stress test: a model that obeys injections and invents numbers → 0 unsafe outcomes in 432 cases.**

## 4. Proof it works (held-out, 432 cases, ES+PT)

| | Keyword bot | Ours (ideal model) | Ours (bad model) |
|---|---|---|---|
| Safe automated resolution | 76.8% | 100% | 64.8% |
| Missed escalations | 24 | 0 | 0 |
| Unsafe outcomes | 0 | 0 | 0 |

- Learned classifier on unseen text: 84.9% vs 62.8% for keywords.
- Honest labels: ideal = upper bound; the live-model run is pending network access.

## 5. Data and engineering rigor
- Contracts with a quarantine gate and rollback; lineage per row, run and partition; incremental loads absorb late arrivals.
- Findings the data dictionary hides: 57% missing USD amounts; 6.6K credit products with no arrears data; 100% broken branch FKs; no MXN at all; transcripts with 42 distinct texts.
- 60 hermetic tests + CI, pinned versions, `make all` rebuilds every number.

## 6. What it takes to make it real
- **Now:** run `make eval-live`; deploy (container ready, 512 MB).
- **Before production:** bank IdP instead of the test PIN; Redis sessions; PII encryption and redaction; metrics stack wired to the specified alerts; voice (85% of contacts are calls).
- **Next workflow:** transaction disputes. Its escalation path and evidence packs already exist.
