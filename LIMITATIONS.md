# Limitations and remaining work before deployment

Written as the honest gap between this 10-day prototype and a live banking
service, and as our own roadmap.

## Not yet measured

1. **The live model on the held-out workload.** The live path has run end to
   end on Claude Opus 5, Sonnet 5 and Haiku 4.5, over 13 fixture turns
   ([`eval/reports/LIVE_SMOKE.md`](eval/reports/LIVE_SMOKE.md)): 1.2–3.0 s p50
   per turn and USD 0.002–0.005 per model call with prompt caching. Groq has
   not run yet: it needs a key. Its default is now the open-weights
   `openai/gpt-oss-120b`, because Llama 3.3 70B left Groq's self-serve tiers
   on 2026-08-16. Still unmeasured on the
   held-out workload, which needs the organizer's warehouse:
   - the model's own tool-selection accuracy (SAR with a live model);
   - p50/p95 latency and cost per case at scale;
   - run-to-run variability.

   What we can show today:
   - the scripted **upper bound**: 100% SAR on the test workload (design v2);
   - an **adversarial lower bound on safety**: 0 unsafe outcomes even with a
     model that obeys injections and invents figures. Under v3 a model's
     figures can no longer reach the customer at all;
   - that the running app degrades safely without the model.

   `make eval-live` produces the missing report once the warehouse is loaded.
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
  numbers is done, and card/account/ID numbers typed by the customer are
  masked in tickets. Still missing are field-level encryption at rest and
  redaction before export to the monitoring stack.
- The external model never receives a customer record
  ([ADR-001](docs/decisions/ADR-001-model-interprets-code-speaks.md)), but it
  does receive the customer's own words, masked. Production would run the
  model under the bank's data-processing terms: provider retention,
  zero-data-retention, region.
- The masking is pattern-based: internal ids, runs of 8+ digits, CURP/RFC
  codes and emails, after normalizing dashes, fullwidth and invisible
  characters. Some things the customer types reach the model as written:
  - a name, an address or an amount;
  - an ID shorter than 8 digits, such as an older Argentine DNI (5.123.456),
    because it cannot be told apart from an amount;
  - two last-4 references separated only by a space ("0001 0002"), which
    read as one 8-digit number and get masked together.

  An amount of 8+ digits is masked for the model but kept in the human
  agent's ticket.
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
- Replies are rendered from templates, not written by the model. They read
  more like a statement than a conversation. That is the price of "no figure
  or action the model invented can reach a customer".
