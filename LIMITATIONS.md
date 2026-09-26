# Limitations and remaining work before deployment

Written as the honest gap between this 10-day prototype and a live banking
service, and as our own roadmap.

## Not yet measured

1. **The live model.** The build sandbox blocks every LLM endpoint we tried
   (Groq, Together, Hugging Face, Ollama). What that leaves unmeasured:
   - the model's own tool-selection and phrasing accuracy;
   - p50/p95 latency with the model in the loop;
   - cost per case;
   - run-to-run variability.

   What we can show today:
   - the scripted **upper bound**: 100% SAR on the test workload;
   - an **adversarial lower bound on safety**: 0 unsafe outcomes even with a
     model that obeys injections and invents figures;
   - that the running app degrades safely without the model.

   `make eval-live` produces the missing report, and it is the first thing to
   run once there is network access.
2. **Deployment.** Not yet deployed (needs a hosting account). The Docker image
   is written but was not built here, because the sandbox has no Docker daemon.

## Data and ML

- **No usable text in the supplied data.** 171K transcripts hold 42 distinct
  customer texts, the text doesn't vary with the contact reason, 100% of agent
  texts contain unrendered placeholders, and there is no Portuguese. So every
  training and evaluation utterance is team-written (2 are real transcript
  sentences). Same-author bias between training and held-out text is likely.
  - Next: sample real (consented, redacted) chat logs, have humans label them,
    and re-run `make train-eval`.
- **Small held-out sets.** 86 utterances in the classifier test split; 432
  cases per system split, with 2–3 phrasings per case type. Intervals are
  wide (e.g. escalation recall 93.3% [70.2–98.8]).
- **Known misses.** "vou processar o banco" escapes the escalation guard, and
  slang is weak (33%). Both are reported, and neither was tuned away on test.
- **Synthetic-data artifacts** limit what the baseline can say:
  - flat intraday demand;
  - an identical 120 s wait for every contact reason;
  - 0% negative sentiment for account/payment contacts only;
  - no MXN products at all.

  Details in docs/data_quality.md.
- **No fraud model.** `fraud_score`/`is_fraud` are shown to the human reviewer
  as evidence but don't drive automated decisions. This workflow escalates
  fraud; it doesn't adjudicate it.

## Security and privacy

- The identity service is a **test IdP**: an HMAC PIN, no MFA, no device
  binding. Production plugs in the bank's IdP and keeps the rest (only tokens
  reach `/chat`).
- `/demo/customers` publishes test PINs for a few sandbox accounts, like any
  sandbox's test login. It must be empty (`DEMO_PUBLIC_CUSTOMERS=`) anywhere real.
- Traces, audit logs and tickets contain customer data. Masking of account
  numbers is done; still missing are field-level encryption at rest and
  redaction before export to the monitoring stack.
- No WAF or bot protection beyond per-session and per-IP rate limits.

## Operations

- **Single process.** Sessions and conversations are in memory; multiple
  replicas need Redis. DuckDB on local disk has a single writer; production
  serves reads from the core system or a replicated store.
- **Ingestion runs at first boot** in the container. Production runs it on a
  schedule into persistent storage.
- **Monitoring is JSONL plus admin endpoints.** The alert thresholds are
  specified (docs/operations.md) but not wired to a metrics stack.
- **Voice is not built.** 85% of account/payment contacts are phone calls; this
  system serves the 15% on text channels until speech-to-text and
  text-to-speech are added.

## Scope, by design

- Read-only. No money movement, no credit decisions (as the brief requires).
  Card blocking, disputes and credit eligibility get an abstain and a pointer
  to the right channel, or an escalation. They are not attempted.
- Portuguese is supported in understanding and replies; the product catalog
  and policies stay Spanish-market.
