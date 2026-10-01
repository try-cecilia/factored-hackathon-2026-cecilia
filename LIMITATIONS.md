# Limitations and remaining work before deployment

Written as the honest gap between this 10-day prototype and a live banking
service, and as our own roadmap.

## Not yet measured

1. **The live models, beyond a sample.** Claude Sonnet 5 and Haiku 4.5 ran on
   132 of the 548 held-out test cases, three runs each
   ([`eval/reports/SYSTEM_EVAL_LIVE.md`](eval/reports/SYSTEM_EVAL_LIVE.md)).
   The intervals are wide (Sonnet 5's safe automated resolution is 95.0%
   [86.3–98.3]), a segment or country cell holds 15–20 in-scope cases, and
   0 unsafe outcomes in 132 bounds the true rate only below ≈2.3%. Groq ran only
   the small sample of item 3; more needs a key. Its default is the open-weights
   `openai/gpt-oss-120b`, because Llama 3.3 70B left Groq's self-serve tiers
   on 2026-08-16.
2. **Deployment.** Deployed on Render since 2026-09-29 (`render.yaml`): the web at
   https://cecil-ai.onrender.com and the API at https://x-payments-agent.onrender.com, one small instance
   each (512 MB). What that leaves out: no replicas, the API loads a 5,000-customer sample rather than the
   whole dataset, and the web calls the API at its public URL, so the API's per-client limits (sign-ins,
   failed keys) count the web's users as one client. CI builds the Docker image and boots it the way Render
   does (a disk mounted owned by root, its own port), then smoke-tests it, checks the disk survives a
   restart, and checks that a first load that fails or is killed leaves nothing a later boot would serve.

3. **Failure handling with a live model.** The reserved failure set (`eval/heldout/`, 226 cases) ran in full with the scripted
   ideal model and the deliberately bad one. With a live model only a small sample ran (Groq's `gpt-oss-120b`, 42 of the
   226 cases and 23 of the generated workload, one run: `eval/reports/LIVE_SAMPLE_GROQ.md`): 0 unsafe, but 3 of 42 not handled as the
   policy asks, and intervals of 20-30 points. That run is not reproducible from artifacts: its selected ids and per-case rows were not
   saved (the tables come from the console output). `eval/live_sample.py` versions the selection, the runner and the table for the next run. `make eval-failures-live` (or `eval-failures-local`) runs all of it.
4. **The reserved set is small and no longer held out for what it found.** Five fixture customers, 17-31 cases per
   category and language: the 95% intervals are 10 to 40 points wide, and 0 unsafe in 226 bounds the true rate
   only below ≈1.3%. Batch 1 was written and committed before the system ran on it; batch 2 after seeing batch 1's
   failures and before fixing them; the fixes came after seeing both. Their post-fix numbers are regression evidence,
   not a held-out measurement, for the failures they fixed. A fresh, human-written set is the remaining fix.
5. **The judge of replies reconstructs templates, from the outside.** By ADR-001 every reply is a fixed template (`agent/core/render.py`) or
   verified facts rendered. Three reviews found that recognising phrases (regex over "ya transferí", "no pude") or matching templates with
   wildcards is always one loophole behind, so `eval/run_system_eval.py` (`reply_template`) now rebuilds, exactly, the replies the system could
   have sent at each turn, and any text that is none of them is `text_outside_the_templates`, unsafe by itself. It rebuilds from: the fixed
   templates; `escalate_unverified` with the turn's own code (`trace_id[:8]`); `render.render_answer` over the turn's verified facts (with the
   customer's catalog labels, or without them for the degraded mode and the baseline); `render.clarify` over the catalog; the trace replies from
   the customer's movements and the run's trace requests; and the `case_*` notices only for a ticket of the customer whose desk state says so.
   What this leaves open:
   - *The orchestrator does not expose the template key or its parameters.* `TurnResult` has the category and the rule, not the message. The clean
     fix is a system change, not made in this branch. Proposal: a field `TurnResult.reply = {"template": "<render.MSG key or 'answer'>", "params": {...}}`
     set at each place that builds a reply (about 15 `TurnResult(...)` calls in `agent/core/orchestrator.py`, and `eval/baseline_bot.py`), never
     serialised by the API; the judge would compare the text to `render.MSG[key][lang].format(**params)` and check each param against the turn's
     data, instead of enumerating candidates. Impact: editing `agent/core/orchestrator.py` changes the policy fingerprint
     (`eval/fingerprint.py`), so `make eval eval-adversarial eval-failures` must be re-run and the three committed reports regenerated; no
     behaviour and no prompt change.
   - *Any free text is unsafe, honest or not.* "No pude registrar tu caso. Comunícate con un agente especializado por teléfono." and
     "O encaminhamento falhou. Seu caso não foi encaminhado." are safe to say and are flagged, like "Ya transferí tu caso". The system never
     writes them; if a later change lets model text reach the customer, every such reply will be flagged until the judge is taught the new source.
   - *The candidates are the customer's real data, not the turn's exact choice.* A `trace_propose` for a movement of the customer's that is not the
     one the system picked passes; so does a `trace_choose` whose options are real movements in any order or subset; and a `case_*` notice passes for any
     status a ticket of the customer has, not the one it should announce at that turn (with no operator acting in the scenarios there is none).
   - *An answer is compared with `render_answer` over the facts the result itself reports.* A wrong fact rendered faithfully is not a text finding
     (it is caught by the ownership and figure checks); and when the facts are missing from the result, a correct-looking answer is flagged.
   - *A quote is excused by rendering.* On a dead session, the exact rendering of a public fact (`get_exchange_rate`) is removed before looking for the
     customer's data; the same figures written another way are not removed, and are flagged.
   The replies measured (548 generated rows in each of the ideal and adversarial runs, and 226 reserved rows in each) contain no text outside the
   templates, trace replies included.
## Data and ML

- **The behavioral deviation shown to the operator does not detect the fraud labels.** Its AUC against `is_fraud` is
  0.504 [0.494, 0.513] (`docs/evidence/behavior_association.md`), under rules frozen before it was computed
  (`docs/BEHAVIORAL_EVIDENCE.md`). It describes how far a movement is from that customer's own history, is labeled so on
  the screen, and routes nothing. It is not evidence that a flagged movement is fraud, or that an unflagged one is not.
  It is also computed per ticket from the customer's whole history (up to 5,000 rows), a read the handoff budget bounds.

- **No usable text in the supplied data.** 171K transcripts hold 42 distinct
  customer texts, the text doesn't vary with the contact reason, 100% of agent
  texts contain unrendered placeholders, and there is no Portuguese. So every
  training and evaluation utterance is team-written (2 are real transcript
  sentences). Same-author bias between training and held-out text is likely.
  - Next: sample real (consented, redacted) chat logs, have humans label them,
    and re-run `make train-eval`.
- **Small held-out sets.** 85 utterances in the classifier test split; 548
  cases in the test split (552 in dev), with 1–3 phrasings per case type and language.
  Intervals are wide (e.g. escalation recall 93.3% [70.2–98.8]).
- **Known misses.** "vou processar o banco" escapes the escalation guard, and
  slang is weak (33%). Both are reported, and neither was tuned away on test
  (`make validate-data-ml` fails if that phrase enters the lexicon).
- **What "no leakage" does and does not show.** Chosen without the test split (the representation by template-grouped cross-validation on the training set plus dev, the threshold on dev), and proven
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
  as evidence but don't drive automated decisions. Measured: `is_fraud` is not learnable from the transaction (AUC 0.506 on a chronological split, [label_signal.md](docs/evidence/label_signal.md)), and `fraud_score >= 70` has 100% precision (999/999) but recalls 23.1% of all frauds (999/4,316; 29.2% of those that carry a score), which is how a score built from the label behaves ([ADR-005](docs/decisions/ADR-005-no-fraud-or-risk-model.md)). This workflow escalates
  fraud; it doesn't adjudicate it.
- **The intent classifier is much weaker on real speech than on our own text.** Zero-shot on 1,090 real calls to an
  e-banking line (MInDS-14, es-ES and pt-PT, ASR transcripts; `docs/evidence/real_speech.md`, protocol fixed before the
  run): on the primary mapping it is right 73.4% of the time against 91.1% for the keyword rules, because it reads 24.6%
  of the out-of-scope requests as needing a person and 11.7% as an in-scope request. On the in-scope calls alone it does
  better than the keywords (89.6% against 81.9%). The runtime escalation guard sent 5.2% [3.9-6.8] of real, non-escalation
  calls to a person, at the edge of the 5% we aimed for. The model was not changed after seeing this: the 84.7% on team-written
  text says nothing about out-of-scope handling on real customers.

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
  BFF. La cola se lee entera (las 200 entradas más nuevas del archivo y, sin importar su antigüedad, todos los casos abiertos o tomados que sigan en el archivo, es decir, hasta que los alcance la retención de 90 días; un caso ya decidido y viejo sale de la lista), se filtra, ordena y pagina en el navegador (25 por página) y se refresca por sondeo cada 30 s, sin
  notificaciones. Tomar, aprobar, rechazar y devolver actúan con un clic, sin diálogo de confirmación, como en el diseño aprobado. El motivo que escribe la persona solo se guarda al rechazar (es lo que la API registra). El diseño muestra una insignia "Demo · synthetic data" que la consola no dibuja: la API no informa si corre en modo demo. La web tiene pocos tests (`make web-test`: el formulario de ingreso, el plazo de la sesión, y pruebas HTTP contra el build de
  producción de CSRF, redirecciones y rotación de sesión, y tests de DOM del panel del caso —sus cuatro estados, el 409 y la marca de evidencia— y de la tabla; el CI los corre con `pnpm test:all`): el resto se verificó con `typecheck`, `build` y un
  recorrido en navegador (`docs/demo/operador-kit-*.png`, en español y portugués, con datos sintéticos de `ops.seed_operator_demo`); con el modelo
  de clientes y un banco real quedaría por probar la carga y la accesibilidad con lector de pantalla.
- `/demo/customers` publishes test PINs for a few sandbox accounts, like any
  sandbox's test login. It exists only with `DEMO_MODE=1` (a 404 otherwise, as does `/admin/demo_pin`).
- `DEMO_MODE=1` turns on the jury sandbox: scenarios with those test PINs, a
  "Why?" that shows policy rules and what the model received, the session's
  own tickets, and buttons that expire the session or take the model down for
  it. Everything acts on the caller's own session, but it is a demo surface:
  it must stay off anywhere real. It is off by default, in the image, in `.env.example`
  and in the compose stack's defaults; `make up` turns it on locally on purpose.
- **Access control is a matrix over shared keys.** `api/access.py` classifies every route by role and the service will not
  start with an unclassified one, but the roles come from three kinds of shared secret in environment variables: one
  admin key for every reader, one metrics token, and named operator keys. There is no per-reader identity for admin
  reads, no rotation other than a redeploy, no MFA, and the counters that stop key guessing live in memory. `/health`
  and `/readyz` are public by design (a probe must reach them) and say which providers are configured and which
  dependency is down, as yes/no. The page's Content-Security-Policy allows inline styles, because the page styles elements
  with `style` attributes. No CORS is configured: a browser app on another origin needs `CORS_ALLOWED_ORIGINS`.
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
- **An internal id typed in lowercase and split is not masked** ("prd fix 0006", "prd_fix_0006"). The masker requires a
  capital letter in the middle of a split id on purpose (so "el cli de 2024" stays as written), and the ownership check
  in the pre-LLM guard uses the same reader. The reserved failure set has it as its one open failure in each language
  (`foreign_id_spelled`): the text reaches the model unmasked, the tool layer refuses the product (`PermissionDenied`,
  handed to a person as a security case), so nothing of another customer's is shown. Organizer ids look like
  `CLI-AB12CD34EF56` (an invented shape): written in lowercase without a split ("prd ab12cd34ef56") they are masked, but split once
  ("prd ab12 cd34ef56") they are not. Reported, not tuned: masking more would also hide ordinary words, and the
  ownership check downstream holds either way.
- **A tool call has no clock of its own.** The orchestrator bounds the model call and the number of tool calls, not the
  time of a tool. The evaluation injects a timeout as the exception a client would raise, and the system hands that to
  a person; a call that hangs would hold its turn until the database driver gives up. DuckDB is local, so it is a
  risk of the production stores that replace it.
- **A broken audit or trace log has two different answers.** If the per-tool audit record cannot be written, the
  lookup fails and a person takes the case (no answer without its audit record). If the per-turn trace record cannot
  be written, the customer still gets the answer and the failure is logged. Both were chosen without the bank's
  policy; the bank may want the second to fail closed too.
- **Web UI kit: checked against Paper by eye and by measurement, not by pixel diff.** The gallery at `/dev/ui`
  (`docs/demo/ui-kit-*.png`) was compared with each Paper artboard; values come from Paper's `get_jsx` and
  `get_computed_styles`. Where Paper draws only one state, the rest was designed in the same language and is listed in
  `docs/integracion.md`: the open "Why?" panel, the failed action result, the hover and selected quick replies, and the
  failed step and error toast of the loaders. Paper draws no "delivered" message state and no skeleton avatar in tables,
  so the kit has neither. The customer chat adds two delivery states Paper does not draw: *unconfirmed* (the answer was lost;
  retrying is safe) and *received* (a 409: the API has the message and only the conversation can show its reply).
- **Chat history keeps figures.** `GET /chat/history` returns the session's last 40 turns as the customer saw them, rendered
  reply included (balances, movements). They live in the conversation state, which the API keeps for 24 hours after a
  session ends (`ConversationStore.RETENTION_SECONDS`) so a restart or a refresh resumes it. Only the live session's token
  reads it, and logging out clears it (the copy in the API's memory expires with the same window and is dropped when the retention job
  purges its row, and a turn of a session that is over writes nothing back); a session that only expires leaves the text in the state until that purge. The
  customer's words are stored with card numbers masked, as in the ticket. Production needs encryption at rest and a
  retention period the bank chooses (or expiry with the session). The demo's "Why?" is not stored: after a reload the
  earlier answers have no explanation.
- **Customer screens: what they cannot know.** The cases in the sidebar are those this conversation opened: there is no
  endpoint that lists a customer's cases across sessions, so a new sign-in starts with none even if the bank still has
  one open. Their status refreshes every 45 s while the page is visible, not by push. The "action result" message is
  recognised by its position (it follows the customer's yes to a proposal) because the API gives every resolved reply
  `category=resolved`; a trace the tracing service did not confirm is drawn as a handoff with its case number, not as a
  red "could not open the trace" card. The keyboard and focus order were checked in a browser and in DOM tests;
  it was not tried with a screen reader. Changing language reloads the route's data (session, history), so with the API down
  it shows the "service unavailable" page with a retry instead of switching.
- **Web UI: the Portuguese was written by the team, not reviewed by a native speaker**, and the interface has only Spanish
  and Portuguese (the assistant's replies come from the API in the customer's language). The customer screens (home,
  sign in, chat) use the kit and i18n; the operator console (`web/src/routes/-operator/`) uses it too.

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
- **Monitoring has metrics, rules and a dashboard, and no production traffic behind them.** `/metrics`, the alert rules
  (`ops/alerts.yml`, checked and unit-tested with promtool) and a Grafana dashboard exist and run in the compose stack.
  Prometheus only evaluates the alerts: no Alertmanager or pager is wired. `python -m ops.alerts` checks the stateless signals through the admin endpoints and can post to `ALERT_WEBHOOK_URL`, but nothing schedules it. The thresholds are the starting values
  in docs/operations.md, untuned. The week-over-week drift rules need eight days of series and have no unit test. A
  per-customer security threshold is not expressible (a label per customer is unbounded): the alert counts in total and
  the customer is found in the traces. Counters are per process and reset on restart, so several replicas would need each
  one scraped, which the single-writer design does not need yet.
- **Retention is applied, not proven at scale.** The purge is tested for every store and runs daily in the container. It
  holds a cross-process lock (`flock` on `<file>.lock`, `agent/filelock.py`) from reading a JSONL file to swapping it in, and
  every writer of those files takes the same lock, so a record confirmed to its writer is not lost to it (tested with a write
  landing exactly at the swap and with a writer in another process). What that does not cover: a process that appends
  without taking the lock (a script of your own), and Windows, where the lock is a no-op. The ticket queue and the desk take
  the lock through a wrapper installed at API start-up (`serialize_policy_writers`), not in their own code, because editing
  `agent/policy/` invalidates the evaluation reports' policy fingerprint and those can only be regenerated against the full
  warehouse; when those files are next changed on purpose they should call `append_line` themselves. SQLite gives freed pages back to
  the file only on a `VACUUM`, which is not run. Backups, if any exist, are outside the policy. Ticket and event
  retention (90 days) is a sandbox stand-in for the bank's regulatory schedule. The warehouse itself holds the customer
  tables and is replaced, not pruned.
- **Reproducible setup, with limits.** Python dependencies are locked with hashes and installed with `--require-hashes`; the
  Docker base images (`python:3.11-slim`, `node:24-slim`, and the Prometheus, Grafana and Ollama images) are pinned by tag,
  not by digest, so a rebuild can take a newer patch release of a base image. `make lock` needs `uv`. The web image runs
  the build with `web/serve.mjs`, a small server of ours; it is tested in the compose stack and the CI, not under production
  load or behind a real edge, and no production host for it is chosen. The stack was verified locally with Docker on macOS
  (OrbStack), and on Linux in the CI (the run of `main` at `2092b29`, 2026-09-29, passed its six jobs on `ubuntu-latest`, the `compose` job
  among them); Docker Desktop was not tried.
- **The local web is checked over HTTP, and by hand in one browser.** `make compose-e2e` drives the web the way a browser does
  (the same requests, cookies and headers: customer login and a chat turn, operator login on the plain form and the queue,
  `/dev/ui` closed), but no browser runs in it. Once, on 2026-09-29, the compose stack was driven with Chromium 154 (customer
  login and a balance question, operator login and the queue): that found that the web's `Referrer-Policy: no-referrer` made the
  browser post `Origin: null` and every operator login a 403, now fixed and pinned by a header check. That run also left a hole
  that Chromium hid: the image is in production mode, so its session cookies were `Secure` `__Host-` cookies over plain `http://`, and
  WebKit (Safari's engine) does not store them, so the login hung. Now the cookies follow `WEB_PUBLIC_ORIGIN` (plain over http,
  `Secure` `__Host-` over https), the compose trusts both `127.0.0.1` and `localhost`, and a login the browser did not keep says so.
  Checked on 2026-09-29 with Playwright 1.63 (WebKit 26.6 and Chromium 153) against a throwaway compose project
  (`ops/browser_cookies_check.mjs`): customer and operator login through both hosts, in both
  engines. **Not tried:** Safari itself (WebKit under Playwright is its engine, not the same build) and Firefox. **Known edge:** a
  `WEB_PUBLIC_ORIGIN` that says https while the browser is on http (a mistake) gets Secure cookies WebKit drops; the customer login
  says the session was not kept, and the operator's refusal notice names the origin to use (it travels in the URL, not in a cookie).
  A list that mixes http and https origins is invalid as a whole.
- **The local model is wired, not measured.** The compose stack can start Ollama and pass the API `LLM_PROVIDERS=local`, and the
  profile was verified with a 0.5 GB model. No evaluation has run against any local model (`gpt-oss:20b` or a smaller one),
  and on macOS Docker runs models on CPU only.
- **The operator screen is tested in pieces, never driven whole.** Its API and components pass their tests
  ([`docs/operator_screen_eval.md`](docs/operator_screen_eval.md)), but nobody has walked queue, claim, approve in a
  browser, and it has had no keyboard or screen-reader pass.
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
  0.62 ≥ τ = 0.55): of the confirm and cancel cases, 4 go wrong (2 confirmations end as a
  balance or out-of-scope reading, 2 cancellations go to a person on the first turn). That is why the ideal model reaches 99.2% and not 100%. It
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
- The operator's side stops at one decision. A case without an action is
  resolved with one message to the customer, who reads it in the case view and
  ahead of their next reply. There are no intermediate states ("waiting for
  the customer", "contacted") and no live chat between operator and customer:
  that needs a push channel (websockets) through the API, the web server and
  the hosting. Both are next steps; the resolution message is the one update a
  customer gets today.
- A message with several requests is answered by the reads the model declares, of which the code runs at most two per
  turn ([ADR-001](docs/decisions/ADR-001-model-interprets-code-speaks.md)). Which reads the model declares is its
  judgment (prompt 3.2.1, rules 9 to 11, with examples in Spanish and Portuguese) and is measured by no committed
  report: the offline evaluation scripts the model and the live evaluation has no compound case. The probe that
  measures it (`ops/probe_compound_requests.py`, criteria written beforehand in `docs/preregistration.md` section 4)
  is run by hand with a provider key. The providers differ: Anthropic's Claude 4 and later call several tools in one
  response by default, while Groq's documentation lists `openai/gpt-oss-120b` and `gpt-oss-20b` (the fallback) without
  parallel tool use, so on the fallback a request for two things may be served with only one of the reads; the
  `parallel_tool_calls` parameter exists but does not add the missing support. Asking for the two things in separate
  messages works everywhere. What the code guarantees is what happens next: the reads that run are
  rendered under their own heading, a clarification for one read does not discard the others (one question per turn;
  the rest are named and kept in the model's history), the reads it did not run are named in a template ("Quedó sin
  atender: ..."), a trace request takes the turn alone wherever it is declared, and a read whose reply would be
  identical to the one just sent gets a notice instead, without losing the note about what was left unattended
  (alternating: asked a third time in a row, the data is shown again, also when the model comes back after an outage). Without the model, a
  compound request is handed to a person, as any request the degraded mode does not read; it does not read
  movements, so it cannot answer "my pending movements" even when the classifier recognizes the intent.
