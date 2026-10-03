# Integration points and contracts of the simulated systems

The brief accepts sandbox services and mock banking tools "when their contracts and limitations are
documented", and asks to identify which inputs are real, de-identified, synthetic or team-generated.
This document does both: it states what is simulated today, which contract each simulation fulfills and **exactly where**
the real system would plug in.

How to read it:

- **Current contract** is what the code does today and a test checks. **In production** is what we propose, not something
  already agreed with a bank. Where it depends on the bank and we do not know, it says **to be defined with the bank**.
- Each boundary uses the same template: *Today*, *Contract*, *Substitution point*, *In production* and *How it is verified*.
- Nothing in this prototype moves real money or makes credit decisions: the brief neither requires nor authorizes it.

## What is real and what is simulated

| Element | Nature | Detail |
|---|---|---|
| Customers, products and transactions | **Synthetic**, supplied by the organizer | Read from a read-only bucket and loaded into the warehouse. The limits of this data are in `docs/data_quality.md` and `docs/dataset-audit.md`. |
| Evaluation cases in Spanish | **Team-generated** | Drawn from the warehouse with computed reference labels (`eval/workload.py`), not written by hand. |
| Turns in Portuguese | **Team-written** | The dataset has no Portuguese; this is a limitation declared in the reports. |
| Human message set | **Real**, from people outside the team | With consent, no personal data (`docs/human_set.md`). Collection is in progress. |
| Customer identity | **Simulated** | Test IdP, see boundary 1. |
| Operator identity | **Simulated** | Named keys, see boundary 2. |
| Trace service | **Simulated** | JSONL file, with an SLA of 2 business days that is a synthetic policy. |
| Case queue | **Simulated** | JSONL file. |
| Trace review rule (90 days) | **Synthetic policy** | Constant `TRACE_REVIEW_AFTER_DAYS`; the final decision is made by a person. |
| Language models | **Real external services** | They only receive masked text, see boundary 6. |

---

## 1. Customer identity

**Today.** `agent/session/identity.py`, `IdentityService.login(customer_id, pin) -> Session`. It is the "trusted test session
service" the brief asks for: a customer number alone does not prove identity.

**Current contract.**

- *Input:* `customer_id` and a second factor. The factor is a 6-digit PIN derived as
  `HMAC-SHA256(DEMO_IDP_SECRET, customer_id)`; the secret lives only on the server.
- *Output:* a session with an opaque token (24 random bytes, 15-minute TTL, `SESSION_TTL_SECONDS`) and the attributes
  `segment`, `country` and `customer_status`. With `STATE_DB_PATH` the session survives a restart and only the token's hash is kept on disk.
- *Errors:* a deliberately generic `AuthError` (the caller does not learn which check failed), `LockedOut` after 5 failures
  in 15 minutes for that customer, and `IdentityUnavailable` if `DEMO_IDP_SECRET` is missing: without the secret no
  session is issued (fails closed). An unknown customer, or one whose account is closed, cannot open a session.
- *Security:* constant-time comparison; the `POST /auth/session` endpoint also limits attempts per source.
- *Lookup and logout:* `GET /auth/session` with the `X-Session-Token` header returns `customer_id`, `session_ref`, the
  attributes and the remaining time, without extending the session (401 if it is not alive). `DELETE /auth/session` revokes it first, then clears the conversation's history as a separate step, and
  answers 204 even if the token does not exist or is already revoked. If the revocation itself fails the answer is an error, never a 204;
  if only the history clean-up fails, the session is still revoked, the failure is counted by type (`/admin/capacity`, `failures`) and the answer is 204.
- *Web frontend:* a BFF keeps the token in an httpOnly cookie and the browser never sees it. It sends the user's IP in
  `X-Client-IP` together with `X-BFF-Secret`, the value of `BFF_CLIENT_IP_SECRET` that the web and the API share; the API
  believes the forwarded address only on a call that carries it (compared in constant time), so the attempt limit is per user
  even when the API is public. Any other caller is told apart by `CLIENT_IP_HEADER` (the edge's header) or its own address.
  Without the secret the forwarded address is ignored. `CLIENT_IP_HEADER=X-Client-IP` still works on a private API that
  only the BFF reaches, but on a public one anyone could choose their own IP.
- *Data:* only the token circulates downstream; tickets and logs carry `session_ref`, a one-way hash.

**Substitution point.** The check inside `IdentityService.login` (`derive_test_pin`). What stays the same: whoever
issues the session always ends up in `SessionStore.issue(customer_id, atributos)`, and the rest of the system only knows the token.

**In production.** The bank's IdP (app login, OTP or IVR PIN), with MFA and device binding;
the attributes would come from the IdP. `/demo/customers` publishes test PINs: it only exists with `DEMO_MODE=1` (404 in every
other case) and must stay off in any real environment.

**How it is verified.** `tests/test_api.py` (login, lookup and logout, attempt limit behind the BFF),
`tests/test_durable_state.py` (sessions after a restart, only the hash on disk).

---

## 2. Operator identity

**Today.** `agent/session/operators.py`, `OperatorDirectory`. Design in
`docs/superpowers/specs/2026-09-29-identidad-operador-design.md`.

**Current contract.**

- *Input:* the `X-Operator-Key` header. Keys are configured in `OPERATOR_KEYS` (`nombre=clave`, that is, name=key).
- *Output:* the operator's name, which **comes from the key and never from anything the operator sends**.
- *Roles:* the admin key only reads; the operator key is the only one that can claim, approve, reject and hand back.
- *Errors:* 503 if no keys are configured, 401 with a missing or invalid key, 429 after too many failures from one source.
  Every failed attempt is recorded in the audit log without the presented key. Repeated names or keys, or keys
  shorter than 24 characters, prevent the service from starting.

**Substitution point.** `require_operator` in `api/main.py`: today it queries `OperatorDirectory`; with SSO it would query the
identity provider and return the same name.

**In production.** Corporate SSO (OIDC) with the bank's roles and MFA. Named keys are an honest bridge,
not the destination: they live in environment variables and are rotated by hand.

**Web operator console** (`web/`, routes `/operador/*`). Human queue, detail with evidence and actions, read-only
monitoring and traces. How the keys are configured:

| Where | What is configured |
|---|---|
| API | `ADMIN_API_KEY` (reads: queue, tickets, monitoring, traces) and `OPERATOR_KEYS=ana=…,beto=…` (acts: claim, approve, reject, hand back). Each operator key is 24 characters or longer. |
| Web (server) | `AGENT_API_URL`, **`WEB_PUBLIC_ORIGIN`** (required in production) and `TRUSTED_CLIENT_IP_HEADER` if there is a proxy, and `BFF_CLIENT_IP_SECRET` (the same value as the API's). **The keys do not go in the web's environment**: each person types their own at `/operador/login`. |
| API and web, behind the BFF | `BFF_CLIENT_IP_SECRET`, the same value on both, as for customer login (the web forwards the user's address, the API believes it only with the secret). Without it, the failed-attempt limit (`OPERATOR_AUTH_FAILS_PER_MIN`) counts by the BFF's IP and ten mistyped keys lock out every operator. A private API that only the BFF reaches may use `CLIENT_IP_HEADER=X-Client-IP` instead. |

- *Reading and acting kept separate, as in the API.* Sign-in asks for the read key and, optionally, the operator key. With
  only the read key the session is **read-only**: it sees everything and cannot act; the console offers to add the
  operator key without signing in again. The operator key is checked with `GET /admin/operator/me`, which returns the name
  it belongs to without touching any ticket; that name is the one the console shows and the one recorded in
  `ticket_events.jsonl`. Sign-in requires the read key because an operator without it could not even see the queue.
- *How the key travels.* It is **typed into a native HTML form** (`<form method="post">`, `type="password"` fields with no
  React state), goes **only once** to the BFF by POST (`/operador/sesion` to sign in, `/operador/clave` to add
  the operator key, `/operador/salir`) and is **never stored in or sent back to the browser**: the BFF checks it against the API,
  keeps it in its memory and answers with a 303 redirect (post/redirect/get) that carries only a destination and, at
  most, a fixed code such as `operator_401` in a single-use cookie. Because it is a native form, it works without
  JavaScript, and no client-side state, store, log or response contains the key. A check backs this up:
  `make web-test` (`pnpm --dir web test:all`) tests the form logic with fake keys, checks that neither the
  destination nor the error code contains them, and fails if a console component keeps a key in state,
  controls a password field or passes a key to a server function. There are also HTTP tests against the handler of the
  production build (`web/tests/http/`, with a fake API): CSRF, hostile redirect destinations and session rotation.
- *Forms protected against CSRF.* The three POSTs (`/operador/sesion`, `/operador/clave`, `/operador/salir`) are rejected,
  without reading the body or touching the session, unless they prove they come from a console page: `Sec-Fetch-Site`, when the browser
  sends it, must be `same-origin`; `Origin` (or `Referer` if it is missing) must be **exactly the public origin**
  (scheme, host and port); with neither header there is no proof and the request is rejected. `SameSite=Strict` was not enough
  for sign-in because there is no cookie yet. The public origin comes from **`WEB_PUBLIC_ORIGIN`** on the web server
  (for example `https://console.bank.example`, without a path), never from proxy headers: an `http://` page on the same host
  cannot force a sign-in over `https://`. **It is required in production**: without it, or with a value that is not an
  http(s) origin, every console POST is rejected and the server logs what is missing.
  **It can be a comma-separated list of exact origins** (scheme, host and port of each): the local Docker stack
  answers on `http://127.0.0.1:3000` and on `http://localhost:3000`, and the compose file passes both by default. Each entry
  must be a pure origin exactly as written: no wildcards, user@, path, query or fragment (the text is validated
  before it is normalized, with the host in ASCII: an internationalized domain goes in punycode, `xn--…`, and Unicode characters that the parser would turn into `*` or `.` are rejected; a trailing `/` is tolerated). **A single invalid entry invalidates the whole value**, and **so does a list that mixes
  http and https** (the cookies cannot be right for both): everything is rejected rather than opening something because of a
  typo. The cookies and the authorization use that same validation. The `X-Forwarded-*` headers are still not read. In production
  it holds **one explicit https origin**. In development, if it is
  empty, the origin of the request URL is used (`http://127.0.0.1:<puerto>`). It is in `web/.env.example`.
  **The rejection is not a blank page:** it is a `303` to `/operador/login?motivo=origen` (or `origen-config`) with the reason in the URL, not in a
  cookie (a browser that does not keep cookies still sees it), taken from a closed list and with no echo of the request: neither the keys nor the origin
  the browser sent; it is also shown if there is already an active session, which is left untouched. In ES and PT: «No pudimos verificar el origen del formulario. Ingresar desde <orígenes configurados>.»
  (We could not verify the form's origin. Sign in from the configured origins.), or, if `WEB_PUBLIC_ORIGIN` is missing or invalid, that the console does not have
  its public origin configured. No session cookie is issued.
- *Cookies by origin.* Whether a cookie is `Secure` and carries the `__Host-` prefix is decided by **`WEB_PUBLIC_ORIGIN`**, not `NODE_ENV`
  (the Docker image runs with `NODE_ENV=production` locally too). With an **https** origin they are `Secure` with `__Host-`
  (`__Host-cecilai_session`, `__Host-cecilai_operator`, `__Host-cecilai_operator_flash`; the language one, `cecilai_lang`, is `Secure`
  without a prefix); with an **http** origin (the local stack, `http://127.0.0.1:3000`) they carry neither, because Safari
  and browsers outside `localhost` do not keep a `Secure` cookie received over http and the sign-in was silently lost.
  Without `WEB_PUBLIC_ORIGIN` in production the previous behavior (`Secure`) is kept. In every case `httpOnly`,
  `SameSite` (`Lax` for the customer session, `Strict` for the operator one) and the forms' origin check remain. It is a single
  function (`web/src/server/cookie-policy.ts`) for the four cookies. If the browser still does not keep the session (cookies
  blocked, http outside localhost), the customer sign-in resets the button and shows «Tu navegador no guardó la sesión…»
  (Your browser did not save the session…), and the operator one (which goes through `/operador/ingreso`, a redirect that looks at the cookie the browser did send)
  returns to the form with the same notice (ES and PT).
- *A new session on every sign-in and every elevation.* A sign-in always creates a new identifier and ends whatever session
  that browser had; adding the operator key also changes the identifier and the previous one stops being valid, so
  a copied read-only cookie does not gain action permissions. The 8-hour cap still counts from the original sign-in. The previous session is consumed in a single step
  (take and delete): of two simultaneous sign-ins with the same cookie only one creates a session; the other returns to sign-in with a
  notice and **without touching the session cookie** (a deletion arriving after the winner's Set-Cookie would leave that session
  orphaned). If the browser lost the winning response, the old cookie is rejected for 30 seconds and is then treated
  as an unknown cookie. No response to a dead identifier (expired, replaced or unknown) deletes the session
  cookie: only an explicit logout deletes it, and a new sign-in overwrites it; that way a slow response to a GET cannot
  delete the session that another sign-in has just set. The same holds for API errors: a 401 on a read (the read key was
  rotated) invalidates on the server only the session that made that request, by identifier and without `Set-Cookie`; 403, 429 and 5xx do not
  end any session. Deleting the cookie is reserved for an explicit logout.
- *Destination after sign-in.* It is decoded and normalized the way a browser would (dots, `%2f`, `%5c`, tabs,
  backslashes) and only a same-site path that does not start with `//` is accepted; when in doubt it goes to `/operador/cola`.
- *Where the keys live.* Never in the browser's JavaScript, in `localStorage` or in a cookie. The web server
  (BFF) keeps them **in memory**, tied to a random 256-bit identifier that travels in an
  `httpOnly` + `SameSite=Strict` cookie (and `Secure` with the `__Host-` prefix when the public origin is https; see "Cookies by origin"). The session expires after 30 minutes without
  activity by the person (the automatic refresh of the queue and of monitoring does **not** count as activity) or after 8
  hours, and is discarded if the API rejects the key (rotated or revoked). On expiry, the console returns to sign-in with a notice.
  `OPERATOR_IDLE_SECONDS` (on the web server, 1800 by default, minimum 10) shortens that window to test expiry.
- *Discarded alternative and why.* A sealed cookie with the keys inside avoids state on the server, but
  puts the keys (encrypted) in the browser, requires a sealing secret that has to be rotated and does not allow closing a stolen session
  from the server. **Cost of the choice:** the sessions live in the memory of a single process, so a restart
  or a second replica without session affinity forces a new sign-in. For a handful of operators this is acceptable; with
  several replicas a shared store (Redis) or a move to SSO is needed.
- *`SameSite=Strict`.* It stops the cookie from being sent from another site, which is the CSRF defense for the actions; the
  cost is that a link to the console from another app (a chat, an email) opens the sign-in first.
- *Errors.* 401 (rotated key) closes the session or asks for the operator key again; 403 on the web means "read-only
  session"; 409 (someone else moved the case, or the screen was stale: each action sends the `version` that was
  seen) reloads the state and shows the conflict panel ("No se aplicó: el caso cambió" (Not applied: the case changed), from `v3` to `v4`, with who moved it); while that notice is
  visible no decision can be made until "Recargar caso" (Reload case) is used. 429 and 503 are explained on screen. Claim, approve, reject, resolve and hand back act with
  one click (as in the approved artboard), with no confirmation dialog: the protection is `expected_version` plus the key's name in the history.
  Resolve is enabled only once the message for the customer has been written.
- *Customer data.* The console shows what the API already returns to the read key: the ticket (with its
  `customer_id`, the truncated request and the evidence) and the customer's context (below). From the traces it does **not** show the answer text, what the
  model saw or the tool arguments: the BFF lets through only a fixed set of fields (`loadTraceLog` and
  `loadTrace` in `web/src/server/operator.functions.ts`).
- *Trying it without real data or model keys:* `python -m ops.seed_operator_demo --dir /tmp/cecilai-operator-demo`
  builds a minimal warehouse, generates new keys and fills the queue and the traces with real turns; it prints the keys and
  leaves `operator-demo.env` to load before `uvicorn`. The screenshots of the walkthrough are in `docs/demo/operador-kit-*.png`.

- *How the screen is built.* It is the approved Paper design (artboards "Operator · Queue" and "Operator · Ticket states", copies in
  `docs/demo/paper-operator-*.jpg`) on top of the kit: a compact sidebar with the views (Todos abiertos, Míos, Sin asignar: all open, mine, unassigned), the seven queues
  with their number of pending cases, and the logs (monitoring and traces); a compact table (`DataTable`) with per-column sorting, status
  tabs, priority, country and language filters, search (`Ctrl`/`Cmd` + `K`) and pages of 25; and the case detail in a tonal
  panel on the right. The filters live in the URL of `/operador/cola` (`vista=mias|sin-asignar`, `cola`, `estado=abiertos|tomados|decididos`,
  `prioridad`, `pais`, `idioma`) and are validated in `web/src/routes/-operator/queue.ts`. The queue is read in the `/_operator` layout (not in the
  queue route) so that the sidebar has its counts on every page; the polling every 30 s also moved there and still goes
  through `refreshQuietly`. The evidence flags as a risk the movements that the API flagged or whose score reaches 70
  (`FRAUD_SCORE_FLAG` in `agent/policy/escalation.py`). The console's texts are in `web/src/i18n/dict/{es,pt}/operator.ts` and
  `monitor.ts`; what comes from the API (the customer's request, reasons, next steps) is shown as is, untranslated.
- *Time in queue and urgency.* The "Edad" (age) column counts from when the case was handed over (`created_at`), and an **open** case that has
  waited longer than its objective is marked in amber with an icon and a text for screen readers (color alone would not reach everyone). The
  "Vencidos" (overdue) button (`vencidos=si` in the URL) keeps only those cases, with their number, and combines with the other filters and the tabs. The
  objectives are in a single table, `TARGET_MINUTES` in `web/src/routes/-operator/sla.ts`, by category family: security
  (`fraud`, `theft`, `account_takeover`, `safety`, `security`, `classifier_escalation`) **15 min**, regulatory (`legal_or_regulator`,
  `compliance_hold`) **2 h**, and the rest (`data_unavailable`, `tool_failure`, `llm_unavailable`, `trace_*` and any new category)
  **4 h**. **They are a demo objective, not a commitment of the bank**: there is no case SLA defined today, and this table is the
  proposal to discuss. The objective measures the wait until a person takes the case, so a case that was taken or decided is not marked
  (so neither `claimed` nor `resolved` ever is). The count uses the minute of `now.ts`, not a clock of its own, and the tests
  (`sla.test.ts`, `queue.test.ts`) fix the time.
- *New cases.* The queue already re-reads itself every 30 s (`refresh.ts`); what arrives in those reads is marked **new** until the
  operator looks at it: a blue dot and the word "Nuevo" (new) for screen readers in the row, `+N` on "Todos abiertos" in the sidebar,
  "N casos nuevos" with the "Marcar como vistos" (mark as seen) button in the queue header, and `(N)` in front of the tab title on every
  page of the console. A case stops being new when it is opened or with that button; re-reading the queue does not count as looking at it. Only
  pending cases count (one that someone else already decided is not news). A tab's first read is its starting point: on entering, everything
  pending is not announced as news. What is "seen" is the list of ids of the tab itself in `sessionStorage`
  (`cecilai.operator.seen`, `web/src/routes/-operator/seen.ts`): it does not touch the API, it ends with the tab and a new tab starts from
  its own first read; without `sessionStorage` (a browser that denies it) the console goes on, with that session's memory. The announcement
  for screen readers is an always-present `role="status"` `aria-live="polite"` region (`NewCasesAnnouncer`) that speaks when the number
  **goes up** (even when it returns to a number already said: 2, 1 and 2 again: the region empties for 150 ms and repeats it) and does not
  move the focus. There is no sound and no browser `Notification` API. It lives in `NewCases.tsx`, with tests in `seen.test.ts` and
  `NewCases.dom.test.tsx`.
- *The customer's context in the case.* Under the evidence, a read-only section with the customer's products (type, currency, status and
  only the **last four digits** of the number), their ten latest movements **plus every pending one**, however old, highlighted (the row and
  the word "Pendiente"), and their other cases and trace requests, with a link to each case. It is served by
  `GET /admin/tickets/{ticket_id}/customer_context` (`api/customer_context.py`), with the **read key** that the queue already uses: the
  operator key does not open it, neither does a customer session, and a case that does not exist gives 404. It reads the warehouse with the
  connection and the data date of `agent/tools/account_tools.py`, but **not through its tools**: those write `str(error)` to the audit log
  when they fail, `/admin/audit_log` serves it, and a message can quote a path, a query or a customer. The query cuts the number to its
  last four digits in the database (the number is never read). It respects freshness like the tools: with `FRESHNESS_ENFORCE=1` and data
  older than `FRESHNESS_SLO_HOURS`, the warehouse block comes out `unavailable`, not current. Pending movements have an explicit cap,
  `PENDING_SHOWN = 100`, far above what a customer holds: if it were reached, the response carries `pending_omitted` and the console says
  "y N pendientes más" (and N more, singular for one). The read is left in the audit log as a `customer_context_read` event with the case, the outcome
  (`ok` or `unavailable`) and, if it failed, only the exception's type. It carries no full number, document, contact, fraud score or
  channel; the product and movement ids are the same ones the console already shows in the pending action. If the warehouse does not answer,
  the response is still 200 with `warehouse.available: false`, and the section says that products and movements are not available and keeps
  the cases and trace requests, which come from other files; the failure is counted (`customer_context_unavailable` in `/admin/capacity`) and
  logged only by the exception's type, never by its message. The console reads it apart from the case (`loadCustomerContext`, which lets
  through only a fixed set of fields, in `web/src/server/customer-context.ts`), after showing the case: a slow or down warehouse neither
  delays nor breaks the panel, and the section offers "Reintentar" (retry). It has its row in the matrix of `api/access.py` and in the table of
  `docs/operations.md`. Tests: `tests/test_customer_context.py`, `web/src/server/customer-context.test.ts`,
  `web/src/routes/-operator/CustomerContext.dom.test.tsx` and, against the production build, `web/tests/http/customer-context.test.ts`: it
  calls the server function the way the browser does (`GET /_serverFn/<id>?payload=`, with `seroval`, the same version the framework uses; it
  is in `dependencies` because the server build imports it at run time and the image installs only those) and checks that without a session
  the API is not asked, that it reads with the read key and not the operator's, that only the fixed fields pass (with decoy fields in the fake
  API), that an invalid id does not reach the API, that without our own origin it is refused, and that a 401 ends that session without
  `Set-Cookie`, a late one too.
- *Walkthrough with screenshots.* With `python -m ops.seed_operator_demo` (cases of different ages, and others added while the console is
  open), in Spanish and Portuguese: `docs/demo/operador-cola-01-vencidos-es.png` to `operador-cola-07-25-filas-detalle-pt.png` (the last two: 25 rows with a case open at 1440×900) (age in
  amber, "Vencidos" filter, new cases with their counter and their button) and `docs/demo/operador-contexto-01-caso-es.png`,
  `operador-contexto-02-caso-pt.png` (the customer section).

**How it is verified.** `tests/test_operators.py`, `tests/test_operator_auth.py` (includes `/admin/operator/me`) and, for the console,
`make web-test web-typecheck web-build` plus the walkthrough with screenshots in `docs/demo/operador-kit-*.png` (`LIMITATIONS.md` says what
it does not cover).

---

## 3. Core banking data

**Today.** A DuckDB warehouse that is **read-only** for the service layer (`agent/tools/db.py`); only ingestion
(`data/pipeline.py`) writes. On top of it there are deterministic functions, with no model, in `agent/tools/account_tools.py`.

**Current contract.** Every function receives `customer_id` as its first argument, taken from the session and **never from what
the model said**.

| Function | Returns |
|---|---|
| `get_customer_profile` | Segment, status and masked product catalog |
| `get_account_summary` | Balances per product |
| `list_transactions` | Movements with filters (maximum 50) |
| `get_payment_status` | Arrears and available credit; cards and loans only |
| `get_exchange_rate` | Exchange rate; if the date is missing, it uses up to 7 days earlier and flags it, or the inverse rate |
| `request_trace` | Pending movements that are candidates for a trace; **opens nothing** |
| `recent_activity_for_review` | Only for the handoff to a human: recent movements with fraud signals |

Rules that each function applies, in code:

1. **Ownership.** If the session's customer does not own the product, `PermissionDenied` is raised (a security
   event, not an empty result). It comes from a database query, never from the user's or the model's wording.
2. **Verification.** It returns a result only if the fields the answer needs exist; otherwise, `DataUnavailable`.
   A valid question that does not apply to the product raises `NotApplicable`, and it is answered instead of transferred.
3. **Minimization.** Account and card numbers leave only with their last 4 digits.
4. **Freshness.** Every result carries `as_of`. With `FRESHNESS_ENFORCE=1`, a warehouse older than
   `FRESHNESS_SLO_HOURS` (36 by default) answers `DataUnavailable` instead of silently returning stale data. On the
   static dataset the policy stays off and every answer states its date; data without an `as_of` date is unavailable either way.
5. **Audit.** Every call is written to the audit log with the trace identifier.

*Error taxonomy* (`agent/tools/errors.py`), each error mapped to a single decision in `agent/policy/router.py`; the
model never decides what a failure means:

| Error | Decision |
|---|---|
| `MissingSlot`, `InvalidArgument`, `ResourceNotFound` | Ask for clarification |
| `NotApplicable` | Answer |
| `PermissionDenied` | Escalate (security) |
| `DataUnavailable` | Escalate (data) |
| Any other error | Escalate (tool failure) |

**Substitution point.** These seven functions. Their signatures and their error taxonomy are the contract; the source can change.

**In production.** A core API or replica, with ownership **verified in the service** (the brief asks to enforce
permissions in the service or tool layer). Ingestion would move from "once at startup" to a scheduled one. The
limits of the current dataset are in `docs/data_quality.md`. Latency, availability and volume: **to be defined with the bank**.

**How it is verified.** `tests/test_tools.py`, `tests/test_pipeline.py`, `tests/test_cross_checks.py`.

---

## 4. Trace service (payment operations)

**Today.** `agent/tools/traces.py`, `TraceService`: a JSONL file (`TRACE_REQUESTS_PATH`). It is the system's **only
action** (ADR-002) and simulates the payment operations service.

**Current contract.**

- *Open:* `open(customer_id, transaction_id, product_id, session_ref)` returns the existing request or a new one, with
  `trace_id`, `status: "open"`, `sla_business_days: 2` (a **synthetic** policy) and `queue: "payments_ops"`.
- *Idempotency:* the `trace_id` is `TR-` plus 16 hex characters of `sha256(cliente|movimiento)` (customer|movement): asking for the same thing twice returns the
  same request, without duplicating it. `find` compares field by field and does not trust an identifier to be unique.
- *Read-back:* the orchestrator reads the request again before telling the customer it exists. If it cannot be read, it does not
  announce it and routes the case to a person (`trace_unverified`).
- *Eligibility:* only movements that are still pending, of type Transfer, Payment or Deposit. One older than 90 days, or
  dated before the product was opened or before the customer registered, is not opened on the customer's "yes": a
  person decides.

**Substitution point.** `TraceService.open`, `find` and `get`.

**In production.** The payment operations API. It needs: an **idempotency key** (customer plus movement) that
returns the already-created request on a retry; immediate read after write, or an explicit "received" status;
and a timeout treated as unverified and passed to a person, without blind retries. The real SLA:
**to be defined with the bank**.

**How it is verified.** `tests/test_trace.py` (includes movements that settle after the proposal, identifier
collisions and a trace that does not read back), and the evaluation judge's review against the service's records.

---

## 5. Case queue and operator work

**Today.** `agent/policy/escalation.py` (`HumanQueue`, `EscalationTicket`) and `agent/policy/desk.py` (`TicketDesk`), on top of
JSONL files.

**Current contract: the ticket.** It is what the brief asks to hand to the human agent: the request, the verified facts,
the actions taken, the evidence and the open questions. Fields: `ticket_id`, `trace_id`, `category`, `priority`,
`queue`, `customer_id`, `session_ref`, `segment`, `country`, `language`, `request` (maximum 500 characters),
`prior_requests` (the last 3, truncated to 160), `reason`, `policy_rule`, `verified_facts`, `evidence`,
`actions_taken`, `open_questions`, `suggested_next_step` and, if there is an action to approve, `pending_action`. The three texts
that the console shows the operator (`reason`, `open_questions`, `suggested_next_step`) also travel as codes, in
`reason_code`, `open_question_codes` and `next_step_code` (below).
**It never carries the session token**, only `session_ref`. The queues are `fraud_ops`, `priority_care`, `complaints`,
`security_review`, `compliance`, `payments_ops` and `account_payments_l2` by default.

**Current contract: the desk.** `TicketDesk.act(ticket_id, action, operator, expected_version, reason, message)` with the
actions `claim`, `approve`, `reject`, `release` and `resolve`. The states are
`open → claimed → approved | rejected | handed_back | stale | resolved`.
The state is the replay of an append-only event log, under a lock. Repeating an outcome already
reached does nothing; any other transition on a closed ticket is a conflict (409); a decision made
from a stale version is rejected; approving checks again that the movement is still pending and reads the trace back. The
customer learning the outcome is covered by `GET /case/{id}` and by a notice on their next message.

- **`resolve`** closes a ticket **without** a pending action with a message for the customer (`message`: stored on a
  single line, 1 to 500 characters, with full card numbers masked). Without a message it is a 400; on a ticket
  with `pending_action` it is a 409, because that one is closed by deciding the action (approve or reject). The desk state
  carries `message`, and the customer reads it verbatim in `GET /case/{id}` and before their next answer ("un agente lo
  resolvió. Mensaje del agente: «...»", that is, an agent resolved it. Agent's message: «...»). The reason for a rejection (`reason`) remains internal.
- A ticket **without** an action that is rejected tells the customer that it cannot be resolved through this channel, without mentioning a
  trace they never asked for.

**Substitution point.** `HumanQueue.enqueue/get` and `TicketDesk.act/state`.

**The operator's texts travel as codes.** The model never writes to the customer (ADR-001), and the text the
operator reads is not written by the model either: it comes from the policy code. That text was in English in `router.py` and
`escalation.py`, and the console showed it as is even when the operator worked in Spanish or Portuguese. Now each
ticket carries the usual English text and, next to it, its code with the parameters:

| Field | What it is |
| --- | --- |
| `reason_code` | `{code, params}` or `null`. It is the code for `reason`. |
| `open_question_codes` | A list with one `{code, params}` (or `null`) for each element of `open_questions`, in the same order. The evidence notes that `escalate` adds go at the end, also with their code. |
| `next_step_code` | The case's category, or `default`. It is the code for `suggested_next_step` (without parameters). |

Contract rules:

- **The English text is kept** (`reason`, `open_questions`, `suggested_next_step`). It is the fallback: a ticket stored before
  the codes does not have the new fields (nothing is rewritten when reading it), a loose text without a code carries `null`, and the
  console shows the English when the code does not exist in its dictionary or lacks the data to build the sentence. It is never left
  empty or hidden.
- **The English text comes from the same catalog as the code** (`agent/policy/notes.py`, one line per code with its
  `{parámetros}`, that is, its parameters), so they cannot diverge.
- **The parameters are what the sentence needs and nothing about the customer**: a category or a list of categories, the number of
  other customers' products, a review reason, the name of the missing field, the error type of a query, the
  classifier's probability. Never the request, an identifier, an amount or a card number; `tests/test_operator_codes.py`
  checks it by escalating a request with a card number, and with the messages of a query exception (with a
  product id and a file path inside). **The raw message of an exception does not travel in the parameters**: it can carry
  internal identifiers and paths and it is in English, so `data_unavailable` carries the missing field (`field`, or the code
  `data_unavailable_unspecified` if it is not known which one), and `tool_failure` and `evidence_failed` carry the error type (`error_type`).
  The message stays only in the English fallback text (`reason`, `open_questions`), as before.
- **What was already a stable identifier gets no new code**: the evidence type (`transaction`, `denied_request`), the
  keys of the facts (`tool`, `result`), the review reason of `pending_action` (`older_than_review_threshold`,
  `before_product_opening`, `before_customer_registration`, `turn_timeout`), `policy_rule` and, in the trace, the outcome and the
  reason of each model attempt and the tools' `error_type`. The console translates them with the same technique, and what it
  does not know it shows as it arrived.

**In the console.** `web/src/routes/-operator/notes.ts` writes each text in the operator's language with the dictionaries
`operator.codes.{reason,question,step}` and `operator.terms.*` (`web/src/i18n/dict/{es,pt}/operator.ts`), which travel in the
operator area, the one the route loads, and also in the trace-detail area. `TicketPanel` uses them for the reason, the
open questions, the next step, the evidence type, the keys of the facts and the review reason; `summary.ts`, for
the summary the operator copies; and the trace detail, for the rule, the attempts and the errors.

**How to add a code.**

1. One line in the catalog of its kind in `agent/policy/notes.py`: `REASONS` (the reason), `QUESTIONS` (an open question), with
   its English text and the `{parámetros}`. The next step is `NEXT_STEP` in `escalation.py`, with the category as the code.
2. Use it where the decision is made: `reason("codigo", parametro=...)` for the reason and `question("codigo", ...)` for the question, in the
   `Decision` of `router.py`. A `Decision` with a loose text still works, but without a code.
3. Its Spanish and Portuguese translation in `operator.codes.<tipo>.<codigo>` of `dict/es/operator.ts` and `dict/pt/operator.ts`
   (the same `{parámetros}` in both languages). A new review reason goes in `operator.terms.reviewReason`, a new
   `policy_rule` in `operator.terms.rule` and in `wholeRules` or `ruleFamilies` of `notes.ts`.

`tests/test_operator_codes.py` fails as long as a catalog code lacks a translation in both languages, and checks that each
question carries its code in its place.

**What the console receives from the queue.** `loadQueue` (`web/src/server/operator.functions.ts`) reads `/admin/human_queue?limit=200` (the 200 newest tickets and, regardless of their age, every one that is still `open` or
`claimed`: a case nobody decided does not leave the queue for being old, but it does leave with retention: after 90 days the ticket
leaves the file and the API no longer sees it) and returns `QueueRow` (`web/src/server/queue-row.ts`) to the browser, not the ticket: `ticket_id`, `created_at`, `category`,
`priority`, `queue`, `customer_id`, `country`, `language`, `request` and, from the desk, only `status`, `operator` and `version`. That is
what the table, its filters, the tabs and the sidebar counters use, and the queue is re-read every 30 s. The evidence,
the verified facts, the actions, the open questions, the pending action and the desk history travel only with
the opened case (`loadTicket`, `/admin/tickets/{id}`). A column or a filter that needs another field adds it to
`QueueRow` and to `toQueueRow`; `queue-row.test.ts` fails if the row starts carrying anything from the case. The queue tolerates a case without
`priority` or without `language` (an old or incomplete record): it is drawn with "Desconocida" (Unknown) as the priority and, for the language, with `?` on screen and "Desconocido" (Unknown) for screen readers and
in the `title` (the column is not wide enough for the word; in the case panel it can be read in full), without hiding it and without assigning it a priority it does not have, and in the default order it comes after the ones that do
have one (`queue.ts`, the kit's `priorityOf`).

**In production.** The bank's case system. It needs: idempotent creation by `ticket_id`; transitions with
optimistic concurrency by version; attaching evidence; and the retention the bank sets (here 90 days is a stand-in).
How real queues and priorities are assigned: **to be defined with the bank**.

**How it is verified.** `tests/test_desk.py` (transitions, stale approval, double approval, retries),
`tests/test_operator_labels.py`, and the handoff tests in `tests/test_orchestrator.py`.

---

## 6. Language model providers

**Today.** `agent/llm/client.py`, `LLMClient`: Anthropic, Groq and Together, in the order of `LLM_PROVIDERS`. One without its key
is skipped.

**Current reliability contract.**

- Each request has a timeout (`LLM_TIMEOUT_SECONDS`, 12 s) and each turn a total time budget
  (`LLM_TOTAL_BUDGET_SECONDS`, 25 s).
- Only transient failures are retried (timeouts, connection, 429, 5xx), with exponential backoff with
  random jitter and no sleep after the last attempt. Permanent ones (authentication, invalid request) move on to the
  next provider.
- A per-provider circuit breaker skips it if it has just failed several times: an outage costs one timeout, not one per request.
- If they all fail, `LLMUnavailable` is raised and the orchestrator escalates or runs in degraded mode. It never answers on its own.
- A daily spending cap (`LLM_DAILY_BUDGET_USD`): once it is exceeded, the system runs as if the model were down.
- A tool call that Groq rejects because of a `null` field is recovered from the error message itself.

**Privacy contract** (the brief forbids private records in external model requests).

- Only what the customer wrote reaches the model, **masked** by `agent/llm/privacy.py`: internal identifiers,
  CURP and RFC, cards and long numbers, emails. The orchestrator never adds a record to the model's context.
- The model **only proposes which tool to use**. Its text is never shown to the customer: the answer is built by the code
  from verified results (ADR-001).
- The evidence is the `records_sent_to_model` metric, which the evaluation measures on every run.
- Known limits: names, addresses and numbers shorter than 8 digits written in free text are not detected
  (`LIMITATIONS.md`).

**Substitution point.** `default_providers` and `candidate_client` in `client.py`. In addition, `agent/core/experiments.py` has shadow and canary ready, to
compare a candidate model with real traffic before switching to it.

**In production.** A model inside the bank's perimeter or an approved gateway, with a data processing
agreement, data residency and key management. Real quotas, latency and cost: **to be defined with the bank**.

**How it is verified.** `tests/test_llm_client.py`, `tests/test_privacy.py`, `tests/test_experiments.py`, the adversarial
evaluation (`make eval-adversarial`, with a deliberately bad model) and the CI quality gate.

---

## 7. Observability, audit and retention

**Today.** `agent/tools/audit.py` and JSONL files under `data/warehouse/`.

**Current contract.** Records are correlated by `trace_id`; what is stored are **execution records**, not the model's hidden
reasoning, which the brief does not accept as an audit artifact.

| Log | Content | Retention |
|---|---|---|
| `audit_log.jsonl` | One line per tool call, the failed key attempts and each retention purge | 30 days |
| `traces.jsonl` | One line per turn: model attempts and their usage, policy applied, latency, cost and cohort | 30 days |
| `ticket_events.jsonl` | Each operator decision, with the operator's name | with the ticket (they are deleted together, once it is out of the queue and its last event is older than 90 days) |
| `human_queue.jsonl` | The tickets | 90 days (stand-in) |
| `trace_requests.jsonl` | The trace requests | 90 days |
| sessions and conversations (SQLite) | Only the token hash; the masked history | expired ones at each purge; 1 day |

Retention is applied by `python -m ops.retention` (one policy for every store, each period in a
`RETENTION_*_DAYS` variable); the container runs it in a daily loop, it is idempotent and each run is recorded as a
`retention_purge` event in the audit log. The read-only endpoints (admin key) are `/admin/human_queue`, `audit_log`,
`trace_log`, `traces/{id}`, `ops`, `llm_budget`, `data_quality`, `drift` and `experiments`. `GET /metrics` (Prometheus format,
with `METRICS_TOKEN` or the admin key), `/livez` and `/readyz` complete the observability, and `ops/alerts.yml` holds the alerting
rules. The rules and a Grafana dashboard run in the local compose stack (`make monitoring-up`); **there is no Alertmanager and no
notification channel connected**. Separately, `python -m ops.alerts` evaluates, through the admin endpoints, the signals that do not
need history and can notify `ALERT_WEBHOOK_URL`, but nothing runs it periodically. Details and commands: `docs/operations.md` (Monitoring, Access control, Data retention).

**Substitution point.** `_JsonlSink.write(record)` in `audit.py`: it is where a SIEM or a log pipeline would receive
each record.

**In production.** A write-only (tamper-proof) destination, with retention by platform policy and
wired alerts. Today **nothing is tamper-evident** (hash chaining is designed, not built), and the
in-memory windows are 1000 audit records and 500 traces.

**How it is verified.** `tests/test_api.py` (the trace log, and that no record exposes the token), `tests/test_drift.py`,
`tests/test_retention.py`, `tests/test_metrics.py` and `tests/test_alerts.py`.

---

## 8. Customer web frontend

**Today.** `web/` (TanStack Start, React 19). The browser never talks to the Python API: a BFF does, with
server functions in `web/src/server/`, and the session token lives in an httpOnly cookie (see boundary 1). The
`/chat` route is the customer chat: the shell (`web/src/shell/`), the conversation (`web/src/chat/`) and the public screens
follow the "Cecil.ai" design from Paper (kit components, no borders, a palette of blues; the only amber is
`--color-caution`, for caution), and their tokens are in `web/src/tokens.css` with the same names as in Paper (`--color-cecil-blue`, `--color-gray-500`,
`--radius-app`...). The operator console must reuse those variables, not redefine them. Nothing depends on the cloud: Inter and DM Mono come
from npm packages (`@fontsource`) and are bundled in the build, and Cecilia's avatar is in `web/public`; there is no CDN and no
Google Fonts.

**How to run it.**

```bash
make web-setup                 # Node 24, pnpm 10.33.2, pinned dependencies
make serve-all                 # with the real warehouse (make ingest or ingest-demo) and a model key
make serve-all-fixture         # no S3 and no keys: the tests' warehouse and a simulated model
```

Web on `http://127.0.0.1:3000`, API on `http://127.0.0.1:8000`. Frontend variables (or `web/.env`):
`AGENT_API_URL` (default `http://127.0.0.1:8000`) and `TRUSTED_CLIENT_IP_HEADER` (see boundary 1). With `DEMO_MODE=1`
in the API, the chat shows, set apart and labeled **Demo**, the guided scenarios, the faults (expiring the session,
model down), "¿Por qué?" (Why?) on each answer and the bank's view of the session; without `DEMO_MODE` none of that is drawn.
`make serve-fixture` sets `DEMO_MODE=1` unless you override it (`DEMO_MODE=0 make serve-fixture`).

`ops/serve_fixture.py` is an **offline simulation**: the code after the model (policies, tools, templates,
tickets, trace requests, sessions) is the real one, but which tool to request is decided by keyword matching, not by a model.
It is useful to develop and show the front end; it says nothing about how a real model behaves.

**Contract the BFF uses.**

| Server function | API call | What it returns to the browser |
|---|---|---|
| `sendMessage` | `POST /chat` with `session_token` (added by the server) and `Idempotency-Key` (one UUID per message, which the client keeps across retries), 35 s timeout | The answer (`disposition`, text, language, `category`, `ticket_id`, and `why` only in the demo) or a failure reason |
| `getHistory` | `GET /chat/history` with the cookie's token | The live session's conversation, already rendered by the API (see below), or `session_expired` / `unavailable` |
| `getCase` | `GET /case/{ticket_id}` | The case status and the update text, or `not_found` |
| `getDemoKit`, `startScenario`, `applyDemoFault`, `getDemoTickets` | `/demo/*` | Only with `DEMO_MODE=1`; the test PINs stay on the server |

The trace proposal is recognized by `disposition=CLARIFY` and `category=confirm_action`, and it is answered with a "Sí" or "No"
that the API code evaluates (never the model). A clarification is drawn as a list of options when the text contains
`1) ...; 2) ...`; if it does not fit that format, the text is shown as is.

**History (`GET /chat/history`).** With the live session's token (`X-Session-Token` header, like `/case`), it returns the turns
the API stored exactly as the customer saw them: their words with card numbers masked, the answer already
assembled by the templates and, per assistant turn, `trace_id`, `disposition`, `category`, `language`, `ticket_id` and
`degraded`, plus, separately, the session's case index (`cases`: `ticket_id`, `category`, `at`), which is not capped along with the turns. Nothing internal: not the rule that decided, not `why`, not what the model received, not the
tool results. It is read-only, the role is CUSTOMER in the `api/access.py` matrix, and the conversation is that session's:
another session, even for the same customer, gets its own (empty if it is new); without a live session, 401. Up to 40
turns are kept (`MAX_TRANSCRIPT`) in the conversation state (`agent/core/orchestrator.py`), which already survives a restart, and they are
deleted on logout. The BFF reads it in the authenticated route's loader, so the server HTML already contains the
conversation: reloading the page does not empty it. On reload the note "Conversación retomada" (Conversation resumed) appears. The `/chat` response
also carries `degraded` (the model was not available and the code answered on its own), which the front end draws as the limited-mode
banner.

**Customer screens** (`web/src/shell/`, `web/src/chat/`; the kit is in the next section).

- *Shell.* Customer sidebar (260 px expanded, or a 56 px rail with the brand button), a bar with the title, the
  language selector and, only in the demo, the "Demo" button. Below 760 px the sidebar is a drawer (menu button, closes with
  Escape, with the backdrop or with its button; focus moves in and returns to the button). The open panel is visible from the first frame (`visibility` with a 0 s transition when opening and a delay when closing): with `visibility: hidden` during the
  animation, Chromium leaves focus on `<body>`. `web/src/shell/drawer-css.test.ts` guards it; in the browser it is checked with normal animations
  (opening the mobile menu and the Demo panel: focus lands on "Cerrar" (Close), Tab stays inside and Escape returns it to the button; screenshots `docs/demo/cliente-27-*` and `cliente-28-*`). Sidebar text and icons are in ink:
  blue is kept for the focus ring and the "unread" dots.
- *Cases.* The section lists the session's cases (the handoffs that arrived with a number, from the history's `cases` index plus those from this page) and the status of each
  one, fetched with `GET /case/{id}` (again every 45 s while a case is still open and the page is visible, and
  when an answer brings an update). The title comes from the handoff's category (`cases.category.*`). "Ver caso" (View case) in the
  handoff message and the case's row in the sidebar open the case view (`web/src/shell/CaseView.tsx`): a modal
  dialog from the right (full screen on a phone) with the reason, the date, the status, what is happening and what comes next
  depending on the status, the latest update written by the API (in the conversation's language) and the number; when it opens, and with
  "Actualizar el estado" (Refresh the status), it requests `GET /case/{id}` again. The API does not keep a history of updates per case, so the
  view does not show one.
- *Messages.* Each answer is drawn with the kit component that its disposition calls for (`resolveMessage`): AUTO_RESOLVE,
  an answer (with "¿Por qué?" only if the API sent `why`, that is, in the demo); CLARIFY, a clarification with options, or the
  trace proposal with Sí/No (`category=confirm_action`); ABSTAIN, a refusal with suggestions; ESCALATE with a case
  number, a handoff to a person; ESCALATE **without** a number (it could not be recorded), "no pude verificar" (I could not verify), with a retry that resends
  the customer's message; the answer to the "yes" to a proposal, the action result; `degraded`, the limited-mode
  banner; a case's updates that the API puts before an answer ("Novedad de tu caso: ...", that is, Update on your case: ...), system notes; session
  ended, "ingresar de nuevo" (sign in again). The action result is recognized by its position (it follows the customer's "yes" to a
  proposal), not by a field: `category=resolved` is shared by every resolved answer.
- *Waiting and delivery.* Three dots until the answer arrives and, after 6 s, the verification steps (one step done, the
  sending, and the one in progress); no text that appears bit by bit. Each customer message carries its state: sending;
  **unconfirmed** (the answer was lost: "Reintentar" (Retry) is safe because it travels with the same key); not sent (429 or a turn
  in progress; also with the same key); and **received** (409, see above): the message the API already has is not resent, and
  "Cargar la conversación" (Load the conversation) is offered, which reads `/chat/history` again. If the answer is not among what the API stored (its last
  40 turns), the message stays "Recibido" (Received) with a text that says so, "su respuesta ya no está guardada y no se puede mostrar" (its answer is no longer stored and cannot be shown), and with no button.
- *Session.* It no longer redirects on its own: when it ends (`REAUTH_REQUIRED` response, 401 or countdown) the chat stays in
  place, with a note, the composer disabled and the "Ingresar de nuevo" (Sign in again) message, which leads to
  `/login?redirect=/chat&motivo=expired`. Another login is another conversation (it starts from scratch).
- *Demo.* With `DEMO_MODE=1` the demo panel is a separate column (a sliding drawer below 1180 px), with the
  Demo label; without the variable it does not even exist in the HTML. The scenarios' titles and hints and the "¿Por qué?" reasons are
  sent by the API in Spanish, English and Portuguese (`title`, `look_for` and `because`, with `pt`); an API without `pt` is shown in Spanish.
- *Language.* Every interface text is in ES and PT (`web/src/i18n/dict/*/{shell,cases,conversation,demo}.ts`); the
  assistant's answers arrive from the API in the customer's language and are not translated. The Spanish does not use the informal
  (tú) imperative (a test checks it).

**Failures, and what the customer sees.**

| Situation | What happens |
|---|---|
| Expired session (`REAUTH_REQUIRED`, HTTP 401 or missing cookie) | The BFF deletes the cookie; the chat shows the "Ingresar de nuevo" (Sign in again) message (see *Session*). With the cookie missing on load, `/chat` redirects to `/login?redirect=/chat` |
| 429 | The message stays "No enviado" (Not sent) with "Reintentar" (Retry) (same key); it is not resent automatically |
| API down, connection cut or timeout | Uncertain outcome: "Sin confirmar" (Unconfirmed), "No pude confirmar si el servicio recibió tu mensaje" (I could not confirm whether the service received your message), with a manual "Reintentar". The retry is safe because it travels with the same key: if the API already processed it, it returns the same answer and does not create another ticket or confirm twice |
| An answer that does not fit the contract | "Recibí una respuesta que no pude mostrar" (I received an answer I could not display) and "Reintentar" (same key) |
| Double send | One turn at a time: the composer is locked while sending, and the BFF rejects a second send from the same session while the first one is running |
| The conversation could not be read on load | A notice with "Reintentar" that requests `/chat/history` again; the rest of the page works |

**Idempotency of `POST /chat`.** With the `Idempotency-Key` header (8 to 64 characters: letters, digits, `-` or `_`), the API
(`api/idempotency.py`) stores the answer per (session, key) while the session lives (`SESSION_TTL_SECONDS`, 900 by
default), in the same SQLite as sessions and conversations (`STATE_DB_PATH`, or memory). The same key returns the same
answer with `Idempotent-Replayed: true`, without running the turn again and without using quota from the message limit; a
retry that arrives while the first one is running waits for its answer. Before a replay is delivered, the API checks that the
session is still alive (also after waiting): with the session closed or expired the answer is `REAUTH_REQUIRED`, as in
a normal turn. The same key with a different text is a 422. Answers for an expired session and errors are not stored. A turn that fails after it has started (for example, the ticket
was already created and the trace log fails) leaves the key marked: the retry gets 409 and never a second turn; the slot is only
given back if the turn was rejected before it started (429, ended session).
After 50,000 stored answers, the oldest lose their answer but keep a marker (a hash of the key):
a retry with that key gets a 409 "already processed" instead of running again, and the UI marks the message
as "Recibido" (Received) and says "El servicio ya recibió este mensaje. Cargar la conversación muestra su respuesta si todavía está guardada" (The service already received this message. Loading the conversation shows its answer if it is still stored):
the turn stayed in the session's history (`GET /chat/history`), even if the answer is no longer in the idempotency table,
as long as it is among the last 40 turns; if it has already left them, after a reload the UI says that the answer cannot be shown. Markers of live sessions are never evicted: with 500,000 keys
retained, a new turn is rejected before it runs (503 with `Retry-After`, no side effects), and each turn takes its slot
in the same transaction that checks the cap. Without the header, the behavior is the same as always. With
`DEMO_MODE=1` the stored answer includes `why` and `policy_rule`, and a replay filters them according to the mode in force.

**Substitution point.** The BFF only knows `POST /chat`, `GET /chat/history` and `GET /case/{id}`; with the real core the contract does not change.

**In production.** A `POST /auth/session/refresh` is missing, to offer "Seguir conectado" (Stay signed in) before the session expires.

**How it is verified.** `make web-typecheck`, `make web-test` (format of the clarifications, sending, 401, idempotency
key, history reading, the conversation logic, every message variant and every delivery state in the DOM,
the shell with its rail and its drawer, and HTTP tests against the build: `/chat` with and without a session, the conversation already in the HTML, ES and PT,
the token that does not leave the server, the demo panel that exists only with the demo), `tests/test_chat_history.py` and
`tests/test_access_matrix.py` (API: the history, that another session does not read it, and its row in the matrix) and `make web-build`. The
full flow was walked through in the browser, in Spanish and Portuguese, on desktop and mobile, with `make serve-all-fixture`; the
screenshots are in `docs/demo/cliente-*.png`: home and login (ES and PT), empty chat, answer with "¿Por qué?", clarification,
refusal, escalated case with the cases sidebar, reload with the conversation, trace proposal and result, limited mode,
chat in Portuguese, rail, tablet, mobile (chat, drawer and demo), message limit, ended session, unconfirmed delivery,
waiting (dots and steps) and the chat without the demo.

### UI kit, i18n and gallery

**How to use the kit.** The components live in `web/src/ui/` and are exported from a single entry point:
`import { Button, DataTable, Sidebar, AnswerMessage, Toast } from '../ui'`. What today only the gallery draws (`Progress`,
`SidebarMenu`, `DataInAnswer`) is not in that entry point and is imported from its own file: every module of the barrel, with its CSS, ships in the
app's initial bundle. A component that the app starts using is added to the `index.ts` of its area. They are presentational (they take props, they do not call
the API), they draw no borders (only the `outline` button and the focus ring) and they consume only variables from
`web/src/tokens.css`; each one brings its CSS alongside, with `ui-*` classes that do not clash with those in `styles.css`. The areas are
`Button` and `IconButton`; `loaders/` (`Spinner`, `ThinkingDots`, `CheckingSteps`, `Skeleton`, `Progress`, `DeliveryStatus`,
`PageLoader`, `Toast`); `sidebar/` (customer, rail, operator, row menu, empty and loading); `table/` (`DataTable`, comfortable
at 48 px and compact at 32 px, selection with `BulkActionBar`, sorting, `Pagination`); `messages/` (one component per
chat variant, and `resolveMessage`, which translates the API's disposition into a variant: AUTO_RESOLVE is an answer,
CLARIFY a clarification, ABSTAIN a refusal, ESCALATE a handoff to a person, REAUTH_REQUIRED sign in again). The
assistant's answers arrive through props already in the customer's language and are not translated. The rule-based logic (sorting, selection,
pagination, delivery states, disposition mapping) is in pure `.ts` files with tests.

**Language.** Spanish (`es`) and Brazilian Portuguese (`pt`). The server resolves it in this order: the `cecilai_lang` cookie,
then `Accept-Language`, then `es` (`web/src/i18n/resolve.ts`); the root route's loader delivers it, so the HTML comes out
in the right language and `<html lang>` is `es` or `pt-BR`. `LanguageSwitcher` stores the cookie (one year, it is not a secret) and
reloads the route's data without reloading the page. The interface's Spanish is neutral for Argentina, Mexico and
Colombia: no voseo and no informal (tú) imperative (infinitives and noun phrases: "Reintentar", "Intentar de nuevo").

**How to add a text.**

1. Write it in the area's Spanish dictionary, in `web/src/i18n/dict/es/<área>.ts` (a nested object; dynamic
   values go as `{nombre}`).
2. Write its translation in `web/src/i18n/dict/pt/<área>.ts`. It is typed against the Spanish one: if a key is missing or there is
   an extra one, `make web-typecheck` fails.
3. Use it: `const t = useT()` and `t('shell.customer', { id })`. Outside React, `translate(messages, clave, params)`, with the
   dictionary that the root loader provides. A route's title uses `headTitle(matches, clave)`, which reads that same dictionary.
   A nonexistent key does not compile.

**Dictionaries per area.** No page downloads all the texts: each one loads, in its language, the key namespaces
(`common`, `shell`, `operator`...) of its area, and nothing else. The areas and their namespaces are in `web/src/i18n/areas.ts`: customer
(`/`, `/login`, `/chat`), operator (`/operador/...`), monitoring (what `/operador/monitoreo` and `/operador/trazas` add) and
gallery (`/dev/ui`, which loads the full dictionaries in its own chunk). The root loader (`routes/__root.tsx`) resolves the
language and the route's area, and the dictionary travels in its data: the server HTML and hydration use the same one, and the
loading and error components of a route have it even if its loader fails. It is loaded again when the language changes and when
entering a page whose area is not loaded (from the queue to monitoring), before drawing it. Therefore:

- A new key in a namespace that already exists needs nothing else.
- A new namespace is a file in each `dict/`, a line in `es.ts` and `pt.ts`, one entry per language in `sources` of
  `areas.ts` and its name in the list of every area that uses it. If a screen uses a key from a namespace that its area does not load,
  the key appears on screen as is; `web/src/i18n/areas.test.ts` follows the imports of each area's routes and fails first.
- A new route outside those prefixes belongs to the customer area: if it belongs to another one, add it in `areasOf` and in `areas.test.ts`.

The cost: the area's dictionary goes inside each page's HTML (about 6.5 kB gzipped for `/chat` or the queue) instead of
a JS file that the browser caches; in exchange, the initial JS no longer carries the texts of the other areas or of the other language.

`make web-test` also checks that both languages have the same keys and the same placeholders, and that the Spanish has no
voseo.

**Gallery.** `/dev/ui` shows each component in all its variants and states, to compare them against the Paper
artboards; with `?both=1` it draws the whole kit in Spanish and in Portuguese. It exists with `make serve-web` (development) or with a
build started with `UI_GALLERY=1`; in any other build it answers 404 and its code goes in a separate chunk that the
client never downloads. The states that can only be reached with the pointer or the keyboard (hover, pressed, focus) are drawn
with the `forceState` prop. The gallery screenshots against Paper are in `docs/demo/ui-kit-*.png`.

The customer screens extended the kit without touching its Paper variants: `DeliveryStatus` adds the *unconfirmed* and
*received* states (with `detail` and `onReload`), `UserMessage` accepts the delivery line and the tint of a message that did not
arrive, and `ConfirmTraceMessage` accepts `disabled` and works without a movement card (the API sends the proposal as text).

---

## Start everything with one command

Everything starts and is tested in local Docker, with no accounts, no S3 and no API keys; the cloud services (S3, Render,
model providers) are options, never requirements.

```bash
make up                 # API + web on the fixtures warehouse; writes .env with new secrets; http://127.0.0.1:3000 and :8000
make env-check          # with an old .env: which .env.example variables it lacks (names only) and whether INGEST_ARGS would read S3; make up runs it as a warning
make env-fill           # adds to .env only the missing ones, with generated secrets; changes nothing that is already there
make monitoring-up      # also Prometheus (with the alerting rules) and Grafana with its dashboard: :9090 and :3001
make up-dataset RAW_DIR=/ruta/a/data/raw   # your local CSVs, mounted read-only, ingested on the first start
make up-llm-local       # also a local model (Ollama in Docker); make up-llm-host uses the host's Ollama
make compose-e2e        # brings everything up from scratch in a separate, disposable project, checks it end to end and tears it down (it is the CI's `compose` job)
make down               # stops the stack; its volumes are kept
make evidence           # regenerates docs/evidence/data_ml_validation.{md,json}; make gate and validate-data-ml verify without writing
make clean-volumes      # also deletes the volumes (asks first)
```

The compose stack's web runs in production mode: the operator console requires `WEB_PUBLIC_ORIGIN`, and the compose file passes it
(by default `http://127.0.0.1:${WEB_PORT}` and `http://localhost:${WEB_PORT}`, along with `TRUSTED_CLIENT_IP_HEADER`, `OPERATOR_IDLE_SECONDS` and `UI_GALLERY`; they are in
`.env.example`). `make compose-e2e` goes in through the web like a browser: customer login and a chat turn, operator login through the
form (with and without the correct `Origin`, and via `localhost`) and their queue, and `/dev/ui` at 404; it repeats this with the web restarted behind an
https origin, where it expects `Secure` cookies with `__Host-`. With a real browser (WebKit, Safari's engine, and Chromium)
it was verified once with `ops/browser_cookies_check.mjs`.

Without a model key the assistant runs in a safe degraded mode: simple balances from verified data and everything else to a
person. RAM and disk requirements of the local models, and why the host's Ollama is the better choice on macOS: `docs/operations.md`
("Local development").

## Remaining work before deployment

This is the consolidated list of what separates this prototype from a real service. The detail of each point is in the
corresponding boundary and in `LIMITATIONS.md`.

1. **Identity:** the bank's IdP with MFA for customers and SSO with roles for operators.
2. **Core:** an API or replica with resource ownership verified in the service, and scheduled ingestion.
3. **Traces:** a payment operations API with an idempotency key and read-after-write.
4. **Cases:** integration with the bank's case system and its regulatory retention.
5. **Models:** a model inside the bank's perimeter, with a data processing agreement.
6. **Observability:** a tamper-proof destination, the alerts in `ops/alerts.yml` connected to a notification channel, and encryption at rest.
7. **Scale:** the state in SQLite has a single writer; several replicas need Redis or Postgres.
8. **Evaluation:** repeat the measurement with real data and traffic. The current figures are offline and from a simulator, and
   **they are not a measured production improvement**.
