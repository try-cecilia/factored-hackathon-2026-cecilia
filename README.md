# LATAM Bank — AI-First Account & Payment Inquiries Agent

**Factored AI & Data Hackathon 2026** submission. An AI-first customer-service
system for one focused banking workflow — **account and payment inquiries**
(balance, transaction history, payment/due status, exchange rates) — for a
LATAM retail bank operating in Mexico, Colombia, and Argentina.

## Why this workflow

Chosen with data, not intuition. We pulled the real `call_center_interactions`
table (686K rows) from the organizer's S3 dataset and found:

| `reason_category` | Share of contacts |
|---|---|
| **Transaccional (account/payment)** | **35.0%** |
| Producto | 22.0% |
| Queja (complaint/dispute) | 17.1% |
| Técnico | 15.0% |
| Comercial (credit/sales) | 8.0% |
| Retención | 3.0% |

Account/payment inquiries is the single largest contact reason in this bank's
own operational data — the highest-volume, most-requested workflow to
automate. See `docs/data_evidence.md` for the full breakdown (including why
transaction disputes was the runner-up).

## What this system does

- Understands a customer's request in **Spanish or Portuguese**.
- Answers balance, transaction-history, payment-status, and exchange-rate
  questions, **grounded only in verified data** — never invented figures.
- Refuses (abstains) anything outside this workflow (card blocking, disputes,
  credit eligibility) and says so.
- Escalates to a human agent — with a structured handoff, not a transcript
  dump — the moment fraud/dispute language appears, a permission check
  fails, or required data is missing.
- Enforces who-owns-what in the tool layer itself, not in the prompt: no
  phrasing convinces it to show another customer's data.

See `ARCHITECTURE.md` for the full Understand → Decide → Act → Verify →
Escalate design, and `LIMITATIONS.md` for an honest account of what a real
deployment would still need.

## Repo layout

```
data/        S3 -> DuckDB ingestion pipeline, data contracts, quality checks
agent/
  core/      orchestrator (the 5-step loop)
  tools/     deterministic account/transaction/payment/fx functions + audit log
  policy/    deterministic routing + escalation handoff builder
  llm/       Groq/Together client, prompts, intent classifier + baseline
  session/   mock auth/session service
api/         FastAPI app (chat endpoint + admin views of the queue/audit log)
eval/        labeled test cases, intent-classifier benchmark, guardrail harness
ops/         Dockerfile, entrypoint, docker-compose
tests/       pytest suite (pipeline idempotency, orchestrator, guardrails)
```

## Running it locally

```bash
cp .env.example .env   # fill in AWS_*, GROQ_API_KEY (see below)
pip install -r requirements.txt
python -m data.pipeline              # ingest the dataset into DuckDB (~1 min)
uvicorn api.main:app --reload
```

```bash
curl -X POST localhost:8000/auth/session -d '{"customer_id":"CLI-XXXX"}' -H 'content-type: application/json'
curl -X POST localhost:8000/chat -d '{"session_token":"<token>","message":"¿Cuál es mi saldo?"}' -H 'content-type: application/json'
```

### A note on the LLM provider in this submission

The core LLM is **Llama 3.1/3.3 via Groq**, with Together AI as a fallback
provider (dual-provider fallback is also our concrete "safe fallback"
reliability evidence, not just a cost hedge). During development, the sandbox
this was built in had outbound network access to `api.groq.com` blocked by
its own environment policy — unrelated to the deployed app, which reaches
Groq normally. Every guardrail scenario, the full orchestration loop, and the
FastAPI layer are proven correct with a scripted LLM stand-in
(`eval/fake_llm.py`), clearly labeled as an **offline simulation** wherever
it's used, per the challenge's own rule against reporting a simulation as a
measured production result. `eval/run_guardrail_eval.py` re-run against the
live model is the one remaining validation step before this can be called
production-tested end-to-end.

## Tests & evaluation

```bash
pytest tests/ -v                            # pipeline idempotency, orchestrator, guardrails
python -m eval.evaluate_intent_classifier    # learned component vs. keyword baseline
python -m eval.run_guardrail_eval            # rubric metrics (offline simulation, see above)
```

## Data access

This submission uses the organizer-provided, read-only S3 dataset
(`factored-datathon-2026-s3-...`), entirely synthetic. Credentials are read
from environment variables (`.env`, never committed) — see `.env.example`.
