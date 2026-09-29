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

## Data and ML

- **No usable text in the supplied data.** 171K transcripts hold 42 distinct
  customer texts, the text doesn't vary with the contact reason, 100% of agent
  texts contain unrendered placeholders, and there is no Portuguese. So every
  training and evaluation utterance is team-written (2 are real transcript
  sentences). Same-author bias between training and held-out text is likely.
  - Next: sample real (consented, redacted) chat logs, have humans label them,
    and re-run `make train-eval`.
- **Small held-out sets.** 85 utterances in the classifier test split; 528
  cases per system split, with 1–3 phrasings per case type and language.
  Intervals are wide (e.g. escalation recall 93.3% [70.2–98.8]).
- **Known misses.** "vou processar o banco" escapes the escalation guard, and
  slang is weak (33%). Both are reported, and neither was tuned away on test
  (`make validate-data-ml` fails if that phrase enters the lexicon).
- **What "no leakage" does and does not show.** Chosen on dev only, and proven
  by changing the test labels and seeing nothing chosen move
  (`docs/evidence/data_ml_validation.md`). Not shown, or done with the test
  split in view:
  - the similarity cut-offs (0.90 excludes, 0.60 lists) were read off the
    distribution of the whole held-out, dev and test together; one phrase
    ("quantos pesos vale um dólar") is left out of scoring because of it;
  - that the held-out set was written after the training data and the keyword
    baseline were frozen is the team's statement: the git history starts with
    a single import commit, so only "the files have not changed since they
    were measured" (their hashes) is checkable;
  - a similarity of characters does not see a paraphrase with other words.
- **Freshness is off in the demo and lightly covered.** The SLO
  (`FRESHNESS_ENFORCE=1`) gates balances, transactions and payment status only;
  the profile and the exchange rate are not gated. Age is counted in whole days
  from the as-of date, which each process reads once (`lru_cache`), so a
  re-ingest into a running server is not seen until it restarts. The dataset is
  a static snapshot, so no real update cadence has been measured.
- **Lineage is a CLI, from this version on.** `python -m data.lineage` follows a
  row to its run, contract and code version, and the SHA-256 of the CSV as it
  was on disk when loaded (after download; the S3 object's own ETag is not
  kept). It is not exposed by the API. A warehouse loaded before
  `_source_files` existed has no hashes and fails `--verify` until it is
  ingested again, and the committed full-run quality report predates it.
- **Rounding is detected to 9 decimals.** A value that the cast would round
  (`200000.005` into two decimals) is quarantined, but the comparison is made
  at 9 decimals, so a difference beyond the 9th digit is not seen.
- **A truncated daily file is set aside whole, with no ids.** The CSV reader
  cannot align a file whose last row is short, so every row of that file goes
  to quarantine with its ids empty (only `_source_file` says where they came
  from). Nothing from it is served, but the quarantine cannot list which
  transactions were lost; the file has to be re-downloaded.
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
- **Consola web de operador.** Las claves las guarda el servidor de la web en memoria (cookie `httpOnly` +
  `SameSite=Strict` con un identificador opaco): un reinicio o una segunda réplica cierra las sesiones, y una clave
  filtrada sigue valiendo hasta rotarla. Cada persona teclea sus claves en un formulario nativo que las envía una vez al BFF (nunca pasan por el
  JavaScript de la página ni vuelven al navegador), así que dependen de que el canal sea TLS. Sin `CLIENT_IP_HEADER=X-Client-IP` detrás del BFF, el límite de intentos fallidos cuenta por la IP del
  BFF. La cola se lee entera (las últimas 200 entradas del archivo) y se refresca por sondeo cada 30 s, sin
  notificaciones ni paginación. La web tiene pocos tests (`make web-test`: el formulario de ingreso, el plazo de la sesión, y pruebas HTTP contra el build de
  producción de CSRF, redirecciones y rotación de sesión; no hay tests de componentes, y el CI no los corre): el resto se verificó con `typecheck`, `build` y un
  recorrido en navegador (`docs/demo/operador-*.png`, con datos sintéticos de `ops.seed_operator_demo`); con el modelo
  de clientes y un banco real quedaría por probar la carga y la accesibilidad con lector de pantalla.
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
- No WAF or bot protection beyond per-session, per-customer and per-address rate limits and the concurrency gate.
- **Web chat: retries rely on an idempotency key.** Each message travels with an `Idempotency-Key` and the API keeps
  the reply for as long as the session lives, so a retry after a lost answer does not file a second ticket or confirm
  twice. Replies live in the single-writer SQLite state like sessions; if that file is lost the turn runs again, and
  past 50,000 kept replies the oldest are dropped and their retries get a 409 instead of a reply. Keys of live
  sessions are never evicted: at 500,000 held keys new turns get a 503 with `Retry-After` until sessions end.
- **Web chat: the conversation does not survive a login.** An expired session ends its conversation with it (the
  API keys it by session), so signing in again starts from zero; there is no "stay signed in" because the API
  has no refresh endpoint. Case status is read on demand ("Actualizar estado"), not pushed.
- **Web chat: contrast and screen readers are checked by hand only.** Text contrast was computed in the browser on
  the chat page (no pair under 4.5:1; oklch/color-mix values it cannot parse are skipped), focus rings and the
  live region were inspected, but no assistive technology or automated audit (axe) has run.

## Operations

- **Single process.** Sessions and conversations are kept in SQLite on the
  persistent disk (`STATE_DB_PATH`), so a restart resumes a case in flight, but
  SQLite has one writer at a time: several replicas need Redis or Postgres.
  Tickets, operator decisions and traces are JSONL files read linearly, and the
  rate limiters, the model budget counter and the provider circuit breakers
  still live in memory and reset on restart. DuckDB on local disk has a single
  writer; production serves reads from the core system or a replicated store.
- **Limits and retries are per process.** The rate limiters (per session, customer and address), the concurrency
  gate, the model budgets and the circuit breakers live in memory of one process: several replicas multiply every
  limit until they share a store. The capacity numbers (docs/operations.md) come from the fixture warehouse with the
  model **simulated** at its measured latency: they show the limits and the behaviour under overload, not the
  provider's own rate limits, which stay unmeasured.
- **Traces are not exported.** Every turn has a correlation id (`X-Request-ID`, `traceparent`), per-stage timings
  and structured logs, in a span-shaped format, but no OpenTelemetry exporter is wired and nothing reads them but the
  JSONL and the admin endpoints. The trace record still holds the reply text and the masked request (see Data
  retention). The server does not time out slow request headers; the edge proxy does.
- **The tracing service is a sandbox.** Its retries and idempotency (trace id derived from customer and movement) are
  written for a service with that contract; a bank's payments-operations API would need its own error mapping and a
  real idempotency key.
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
