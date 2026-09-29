# Limitations and remaining work before deployment

Written as the honest gap between this 10-day prototype and a live banking
service, and as our own roadmap.

## Not yet measured

1. **The live models, beyond a sample.** Claude Sonnet 5 and Haiku 4.5 ran on
   132 of the 528 held-out test cases, three runs each
   ([`eval/reports/SYSTEM_EVAL_LIVE.md`](eval/reports/SYSTEM_EVAL_LIVE.md)).
   The intervals are wide (Sonnet 5's safe automated resolution is 95.0%
   [86.3–98.3]), a segment or country cell holds 15–20 in-scope cases, and
   0 unsafe outcomes in 132 bounds the true rate only below ≈2.3%. Groq has
   not run: it needs a key. Its default is the open-weights
   `openai/gpt-oss-120b`, because Llama 3.3 70B left Groq's self-serve tiers
   on 2026-08-16.
2. **Deployment.** Not yet deployed: it needs the hosting account. The Render
   Blueprint (`render.yaml`) is ready, and CI builds the Docker image on every
   push and boots it the way Render does (a disk mounted owned by root, its
   own port), then smoke-tests it, checks the disk survives a restart, and
   checks that a first load that fails or is killed leaves nothing a later
   boot would serve.

3. **Failure handling with a live model.** The reserved failure set (`eval/heldout/`, 226 cases: expired sessions,
   unauthorized access, prompt injection, tool failures, ES/PT ambiguity) ran with the scripted ideal model and the
   deliberately bad one, never with a live model: it needs a key (or a local Ollama model), and none was available
   where it was written. `make eval-failures-live` (or `eval-failures-local`) runs the same cases on one. So it measures
   the deterministic layers and whether safety depends on the model; it says nothing about what a live model
   understands from these phrasings.
4. **The reserved set is small and no longer held out for what it found.** Five fixture customers, 17-31 cases per
   category and language: the 95% intervals are 10 to 40 points wide, and 0 unsafe in 226 bounds the true rate
   only below ≈1.3%. Batch 1 was written and committed before the system ran on it; batch 2 after seeing batch 1's
   failures and before fixing them; the fixes came after seeing both. Their post-fix numbers are regression evidence,
   not a held-out measurement, for the failures they fixed. A fresh, human-written set is the remaining fix.
5. **The full-warehouse reports are stale after the failure-handling fix.** The fix touched `agent/core/orchestrator.py`,
   so the policy fingerprint changed and `eval/gate.py` fails until `make eval eval-adversarial` is re-run on the
   organizer's warehouse. Nothing in the generated workload's outcomes should move (the fix changes only exception
   paths and one degraded-mode word list), but that is a claim, not a measurement, until it is re-run.

## Data and ML

- **No usable text in the supplied data.** 171K transcripts hold 42 distinct
  customer texts, the text doesn't vary with the contact reason, 100% of agent
  texts contain unrendered placeholders, and there is no Portuguese. So every
  training and evaluation utterance is team-written (2 are real transcript
  sentences). Same-author bias between training and held-out text is likely.
  - Next: sample real (consented, redacted) chat logs, have humans label them,
    and re-run `make train-eval`.
- **Small held-out sets.** 86 utterances in the classifier test split; 528
  cases per system split, with 1–3 phrasings per case type and language.
  Intervals are wide (e.g. escalation recall 93.3% [70.2–98.8]).
- **Known misses.** "vou processar o banco" escapes the escalation guard, and
  slang is weak (33%). Both are reported, and neither was tuned away on test.
- **Synthetic-data artifacts** limit what the baseline can say:
  - flat intraday demand;
  - an identical 120 s wait for every contact reason;
  - 0% negative sentiment for account/payment contacts only;
  - no MXN products at all.

  Details in docs/data_quality.md.
- **Customers and products are one snapshot each.** The dictionary announces
  monthly snapshots, but only one file per table was delivered, and some
  `last_updated` values fall after the data's as-of date. Balances and statuses
  are therefore the latest state, not what was true when a past contact or
  transaction happened, so they are never used as historical features.
- **No fraud model.** `fraud_score`/`is_fraud` are shown to the human reviewer
  as evidence but don't drive automated decisions. This workflow escalates
  fraud; it doesn't adjudicate it.

## Security and privacy

- The identity service is a **test IdP**: an HMAC PIN, no MFA, no device
  binding. Production plugs in the bank's IdP and keeps the rest (only tokens
  reach `/chat`).
- **Identidad de operadores.** Los operadores se autentican con claves con nombre (`OPERATOR_KEYS`); el
  nombre en el registro sale de la clave, no de lo que envíe el operador, y leer (clave de admin) está
  separado de actuar (clave de operador). Sigue sin haber MFA, las claves viven en variables de entorno
  y se rotan a mano, y el límite de intentos fallidos está en memoria y se reinicia con el proceso. El
  camino a producción es SSO corporativo (OIDC) con los roles del banco.
- `/demo/customers` publishes test PINs for a few sandbox accounts, like any
  sandbox's test login. It must be empty (`DEMO_PUBLIC_CUSTOMERS=`) anywhere real.
- `DEMO_MODE=1` turns on the jury sandbox: scenarios with those test PINs, a
  "Why?" that shows policy rules and what the model received, the session's
  own tickets, and buttons that expire the session or take the model down for
  it. Everything acts on the caller's own session, but it is a demo surface:
  it must stay off anywhere real.
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
    read as one 8-digit number and get masked together;
  - an identifier spelled out letter by letter ("P R D - F I X 0 0 0 6") or
    an email written as "ana(at)mail.com".

  The masking errs on the side of hiding: an amount range written as one
  chain of digits ("1500-2000", "1.000 - 5.000"), a compact date
  ("20240115") or two ISO dates joined by "/" read as one long number and are
  masked. The model then works without them (it asks, or the customer
  rephrases); nothing leaks. An amount of 8+ digits is masked for the model
  but kept in the human agent's ticket.
- The eval's privacy judge (`records_sent`) is pattern-based too, with its
  own code. It does not see a figure written as a bare integer under 100 (it
  reads those as days, counts or option numbers), an identifier spelled out
  letter by letter, an id the warehouse does not have, or a record value that
  is one of the words the system itself writes into every request (a merchant
  called "Banco"). It does not count
  what customers typed about themselves, such as their name or an amount:
  that is the customer speaking, not the system leaking. It always counts
  ids, 8+ digit numbers, emails and document numbers, because the system
  must mask those even when the customer types them.
- No WAF or bot protection beyond per-session and per-IP rate limits.
- **An internal id typed in lowercase and split is not masked** ("prd fix 0006", "prd_fix_0006"). The masker requires a
  capital letter in the middle of a split id on purpose (so "el cli de 2024" stays as written), and the ownership check
  in the pre-LLM guard uses the same reader. The reserved failure set has it as its one open failure in each language
  (`foreign_id_spelled`): the text reaches the model unmasked, the tool layer refuses the product (`PermissionDenied`,
  handed to a person as a security case), so nothing of another customer's is shown. Organizer ids look like
  `***REMOVED***`: written in lowercase without a split ("prd 04di2iny5hzt") they are masked, but split once
  ("prd 04di 2iny5hzt") they are not. Reported, not tuned: masking more would also hide ordinary words, and the
  ownership check downstream holds either way.
- **A tool call has no clock of its own.** The orchestrator bounds the model call and the number of tool calls, not the
  time of a tool. The evaluation injects a timeout as the exception a client would raise, and the system hands that to
  a person; a call that hangs would hold its turn until the database driver gives up. DuckDB is local, so it is a
  risk of the production stores that replace it.
- **A broken audit or trace log has two different answers.** If the per-tool audit record cannot be written, the
  lookup fails and a person takes the case (no answer without its audit record). If the per-turn trace record cannot
  be written, the customer still gets the answer and the failure is logged. Both were chosen without the bank's
  policy; the bank may want the second to fail closed too.

## Operations

- **Single process.** Sessions and conversations are kept in SQLite on the
  persistent disk (`STATE_DB_PATH`), so a restart resumes a case in flight, but
  SQLite has one writer at a time: several replicas need Redis or Postgres.
  Tickets, operator decisions and traces are JSONL files read linearly, and the
  rate limiters, the model budget counter and the provider circuit breakers
  still live in memory and reset on restart. DuckDB on local disk has a single
  writer; production serves reads from the core system or a replicated store.
- **Ingestion runs at first boot** in the container. Production runs it on a
  schedule into persistent storage.
- **Monitoring is JSONL plus admin endpoints.** The alert thresholds are
  specified (docs/operations.md) but not wired to a metrics stack.
- **Voice is not built.** 85% of account/payment contacts are phone calls; this
  system serves the 15% on text channels until speech-to-text and
  text-to-speech are added.

## The action

- The one action, tracing a pending movement
  ([ADR-002](docs/decisions/ADR-002-one-action-confirmed-in-code.md)), runs
  against a **sandbox tracing service**: JSONL next to the human queue. The
  2-business-day deadline is a synthetic policy. A bank plugs its
  payments-operations API behind the same `open` and `get` calls.
- Only pending transfers, payments and deposits are traced; a pending card
  purchase just posts.
- Only a plain yes or no counts as an answer to the proposal. "Sí, y además
  dime mi saldo" drops the proposal, and the customer has to ask again.
- The pre-LLM intent classifier predates the action. It reads 1 of 12
  team-written trace requests as a possible dispute ("necesito que rastreen
  un pago que no se acreditó"), and that customer goes to a person: safe, but
  not self-served. Retraining with trace examples fixed it but lost a fraud
  report on the classifier's held-out test ("no reconheço essa compra"), so
  the classifier was kept. That choice was made after seeing the test split.
- On the system test split the same guard reads one of the workload's trace
  requests, "hice un pago que sigue pendiente", as a possible dispute (p =
  0.62 ≥ τ = 0.55): 6 of the 48 confirm and cancel cases go to a person on the
  first turn. That is why the ideal model reaches 98.8% and not 100%. It
  shows on dev as well (4 cases). The candidate fix is the one above,
  retraining with trace examples, which cost a fraud report; so it stays
  reported, not tuned.
- The demo's trace scenario starts by clearing the customer's earlier trace
  requests (`clear_traces`, sandbox only), because idempotency is per
  customer and every jury member runs the same test customer.

## Scope, by design

- No money movement, no credit decisions (as the brief requires). Besides
  handoff tickets, the only write is the trace request above.
  Card blocking, disputes and credit eligibility get an abstain and a pointer
  to the right channel, or an escalation. They are not attempted.
- Portuguese is supported in understanding and replies; the product catalog
  and policies stay Spanish-market.
- Replies are rendered from templates, not written by the model. They read
  more like a statement than a conversation. That is the price of "no figure
  or action the model invented can reach a customer".
