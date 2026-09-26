# Limitations & what's left before this is a real product

Honest account, per the challenge's own requirement ("an honest account of
the work required before deployment"). This doubles as our own roadmap if
this goes from hackathon prototype to something we take to a bank.

## Not yet validated

- **Live LLM calls.** This was built in a sandbox whose network policy
  blocked `api.groq.com` (and every alternative we checked: Together,
  Hugging Face, Ollama — see chat history/commit log for the trail). The
  entire orchestration loop, all guardrail scenarios, and the FastAPI layer
  are proven correct against a scripted LLM stand-in
  (`eval/fake_llm.py`), and the app *did* correctly fail safe (auto-escalate)
  when both real providers were unreachable in one live test — but real
  p50/p95 latency, real per-case token cost, and the model's own judgment
  quality on ambiguous phrasing are still unmeasured. Re-running
  `eval/run_guardrail_eval.py` (adapted to hit the live client) against Groq
  is the single highest-priority next step.

## Data / ML

- **Intent classifier dataset is tiny and team-authored** (119 utterances,
  template-generated ES/PT), not derived from the real dataset — the
  dataset's own intent-adjacent fields (`reason_category`, 6 broad buckets;
  `call_transcripts.detected_intents`, unstructured) don't carry this
  workflow's routing granularity. At this size, the deterministic
  keyword-rule baseline currently beats the learned TF-IDF classifier on
  accuracy (87% vs. 79%); both hit 100% recall on the safety-critical
  `requires_escalation` class. Production would replace this with the bank's
  own labeled interaction logs (tens of thousands of examples), which should
  favor the learned approach far more clearly.
- **No fraud/risk model.** `is_fraud`/`fraud_score` in `transactions` are read
  but not used to influence disposition — a real deployment doing anything
  near transactions should have its own fraud-detection integration, out of
  scope here (this workflow explicitly abstains/escalates on any fraud
  signal rather than reasoning about it).

## Security / access control

- **Mock session/auth** (`agent/session/auth.py`) is an in-memory token
  store standing in for the bank's real identity provider. No MFA, no
  device binding, no rate limiting on `/auth/session` (which, as built,
  will issue a token for any customer_id with zero verification — this is
  explicitly a test fixture, not something to expose publicly).
- **No PII redaction pass** on the audit log or human-queue JSONL files —
  they contain real-looking (synthetic) names/balances/transaction detail.
  Production needs field-level encryption at rest and redaction before
  anything reaches a human agent's screen without need-to-know.
- **DuckDB is single-writer, single-file.** Fine for a prototype; a real
  deployment needs the OLTP source of truth (the bank's core banking system)
  kept separate from whatever analytical store backs this agent, with
  proper concurrent access.

## Operations

- **No rate limiting, no multi-tenancy isolation, no autoscaling story.**
  The FastAPI app is a single process; the in-memory session store does not
  survive a restart or scale across replicas (would need Redis or similar).
- **Cold-start data ingestion.** The Docker entrypoint re-ingests the full
  dataset from S3 if no warehouse file exists — acceptable for a demo, not
  for production (needs a persistent volume/object store and a scheduled
  refresh job, not a re-ingest-on-boot).
- **No monitoring/alerting wired up** beyond the audit log and human queue
  being readable; no dashboards, no paging on unsafe-outcome spikes.

## Scope, by design

- No money movement, no live lending decisions (per the challenge's own
  rules) — this workflow only ever reads and reports.
- Card support, transaction disputes, and credit eligibility are explicitly
  out of scope for this submission and are abstained on, not attempted.
- Portuguese test coverage is team-authored/translated, not derived from the
  dataset (which is Spanish-only) — flagged wherever it appears, per the
  challenge's own language-coverage-limitation requirement.
