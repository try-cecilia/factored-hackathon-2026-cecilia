# Security

This is a hackathon prototype over synthetic data, not a bank's production service. This file says which security
controls exist in the code today and which do not. The requirement-by-requirement evidence is in
[`docs/asvs-level1-checklist.md`](docs/asvs-level1-checklist.md).

## Reporting a vulnerability

Tell the team directly; do not open a public issue, and do not put credentials or personal data in a report. We make no
promise about response time: this is a prototype with no on-call.

## What we hold ourselves to

- **Standard.** OWASP ASVS 4.0.3 **Level 1**, walked in full. We make no claim about Level 2.
- **Identity.** A national id or customer number never proves identity. Access is bound to a short-lived session
  minted only after a credential check: a customer's session ends 15 minutes after it is issued, in use or not, and using it does not
  extend it; an operator's console session ends after 30 idle minutes or 8 hours.
- **Decisions are code, not prompts.** The model reads and writes language; eligibility, routing, confirmation and every
  side effect are deterministic code with stable reason codes ([ADR-001](docs/decisions/ADR-001-model-interprets-code-speaks.md),
  [ADR-002](docs/decisions/ADR-002-one-action-confirmed-in-code.md)).
- **Side effects.** A write needs the customer's explicit confirmation of that exact action, an idempotency key, and a
  read-back before it is reported as done.
- **Data minimization.** Ids and card numbers are masked before text leaves for a model; numbers leave the tool layer as
  their last 4 digits (`agent/llm/privacy.py`, `agent/tools/account_tools.py`).
- **Fail closed.** No operator keys, no session secret, or an unclassified route: the service refuses or does not start.

## Implementation status

| Control | Status | Where |
|---|---|---|
| Sessions bound to a credential check; 192-bit tokens, stored hashed; logout, revoke and expiry | Implemented | `agent/session/`, `tests/test_api.py` |
| Access matrix: one row per route, four separate credentials, startup refuses an unguarded route | Implemented | `api/access.py`, `tests/test_access_matrix.py` |
| Operator actions attributed to a named key, never to a field the operator sends | Implemented, no MFA | `agent/session/operators.py` |
| The jury demo's console (`/demo/desk/*`): a visitor resolves, as the bank, the cases their own session filed. Only with `DEMO_MODE=1` and `DEMO_CONSOLE=1`, each exactly `1` (any other value is the 404 of a route that does not exist, and startup refuses a console route without both switches); the credential is the customer's live session of an account in `DEMO_PUBLIC_CUSTOMERS`, with no operator key or session on the path; every ticket must have been filed by the caller's session, checked in the API (another visitor's is the same 404 as none); the customer's context, the chat's news of a case and `/case/{id}` are limited to that session on a public account; the actor is always `demo`, never a field of the body, and no real operator may be named `demo`; with a switch off, any request under `/demo/desk` is the 404 of a missing route; per-session and per-account rate limits | Implemented, for the sandbox only; limits below (gap 10) | `api/demo_desk.py`, `api/access.py`, `agent/core/orchestrator.py`, `tests/test_demo_desk.py`, `tests/test_access_matrix.py`, `tests/test_desk.py` |
| Model never decides or acts; replies are templates or verified facts | Implemented | ADR-001, `agent/core/render.py` |
| One confirmed action, idempotent, read back | Implemented | ADR-002, `api/idempotency.py` |
| Masking of customer text before a model | Implemented, with known holes | `agent/llm/privacy.py`, `LIMITATIONS.md` |
| Input limits: field schemas with an allow list for the customer id and the PIN and a range for the ticket version, a 16 KiB body cap on the API and on every web POST, per-session, customer and address rate limits, bounded concurrency | Implemented, per process; free text is bounded in length, not in characters | `api/main.py`, `api/middleware.py`, `web/serve.mjs`, `tests/test_api.py`, `tests/test_desk.py`, `tests/test_capacity.py`, `web/tests/http/serve.test.ts` |
| API headers: CSP, `nosniff`, no framing, no referrer, `no-store`; CORS off by default, wildcard refused | Implemented | `api/security.py`, `tests/test_security.py` |
| Session cookie: `httpOnly`, `SameSite=Lax`, `Secure` and `__Host-` on https | Implemented | `web/src/server/cookie-policy.ts` |
| Origin check on the operator's form posts (login, add key, sign out) and on the operator's five decisions on a ticket (claim, approve, reject, release, resolve), which are server-function calls: the same check, as a middleware of `actOnTicket` | Implemented; the customer's server functions do not have it (next row) | `web/src/server/origin-check.ts`, `web/src/server/same-origin.ts`, `web/tests/http/csrf.test.ts`, `web/tests/http/csrf-actions.test.ts` |
| Cross-site calls to any server function, the customer's login and chat included, answer 403 | Implemented by the framework's CSRF middleware, registered explicitly in `web/src/start.ts` (a start instance replaces the framework's default, so without that line there would be none); not a check of ours | `web/src/start.test.ts` (it is registered), `web/tests/http/csrf-customer.test.ts` (sign-in function), `web/tests/http/csrf-actions.test.ts` (the five decisions) |
| Web server cache policy: `Cache-Control: private, no-store` and `Pragma: no-cache` on everything the app answers (pages, server functions, errors, redirects), set over whatever the framework says; the build's hashed files under `/assets/` stay public and immutable, the other files of the build public for five minutes | Implemented in the production server (`web/serve.mjs`); not in Vite's dev server, and not measured on the live deployment | `web/serve.mjs`, `web/tests/http/private-cache.test.ts` |
| Errors of server functions: an unexpected exception reaches the browser as `internal error`, without its message, its cause or the API's body; only the validators' messages (`PublicError`) travel. A transport failure or a body that breaks the contract is a status (502, 503) with no message. For the operator's calls to the API (`call` in `operator-api.ts`: every read of the console and the decisions on a ticket), the API's `detail` leaves only for a 400 or a 409, the two the console shows; any other status, a 5xx included, leaves without it | Implemented | `web/src/server/rpc-guard.ts`, `web/src/server/fail-safe.ts`, `web/src/server/operator-api.ts`, `web/tests/http/rpc-errors.test.ts`, `web/tests/http/rpc-errors-operator.test.ts` |
| Customer sign-out in the web: leaving removes the cookie of that browser always, whether or not the API confirms the revocation (the answer says which, and the sign-in page tells the person). A login of another tab that finished meanwhile is closed in that browser too, and its token, like one whose revocation was not confirmed, stays valid in the API until it expires (15 minutes by default, `SESSION_TTL_SECONDS`). A late 401 of an old token, a passive read, never deletes the cookie of a newer login | Partial: the browser is always signed out; the API session may outlive it until it expires | `web/src/server/auth.functions.ts`, `web/tests/http/logout-customer.test.ts`, `web/tests/http/rotation-customer.test.ts` |
| Redirect targets: only a normalized path of this site | Implemented | `web/src/server/safe-path.ts`, `web/tests/http/login-redirect.test.ts`, `web/tests/http/redirect.test.ts` |
| Web headers: `nosniff`, no framing, referrer policy, a CSP without `script-src`, HSTS when every `WEB_PUBLIC_ORIGIN` is https (read with the origin check's parser) | Implemented, CSP partial | `web/serve.mjs`, `web/public-origins.mjs`, `web/tests/http/serve.test.ts` |
| Web server: static files only with a known extension, health check GET and HEAD only, plain-text answers with a charset | Implemented | `web/serve.mjs`, `web/tests/http/serve.test.ts` |
| Tool audit, traces, tickets with a one-way session reference; retention loop that audits itself | Implemented; the records still hold customer data | `ops/retention.py`, `docs/operations.md` |
| Containers run unprivileged (API drops to `agent` with `setpriv`; web runs as `web`) | Implemented | `ops/entrypoint.sh`, `ops/Dockerfile.web` |
| Dependencies pinned with hashes | Implemented | `requirements.txt`, `pnpm-lock.yaml`, `make lock-check` |
| Dependency vulnerability scanning: `pip-audit` over the serving lock (`requirements.txt`) and `pnpm audit --prod --audit-level high` fail the build on a known vulnerability | Implemented for those two; the tracking stack (`requirements-tracking.txt`), the web's development dependencies and moderate or low advisories are not scanned; no update bot | `.github/workflows/ci.yml` (`audit`) |
| Secret scanning | Partial: every blob is scanned when the public repository is exported, not in CI | `ops/export_public.py` |
| CI actions pinned by commit SHA | Implemented | `.github/workflows/ci.yml` |
| Red-team of the assistant (injection, other customers' ids, unauthorized access) | Done, on the assistant only | `tests/test_red_team.py`, `docs/red_team.md` |
| Penetration test, TLS and header test of the live deployment | **Not done** | |

## Known gaps

1. **No secret scanning in CI** (V14.2.1 is Partial: it is met only for the serving lock and the web's production tree at high or critical, see the scanning row above). Secrets are scanned only at the public export.
2. **The web server's CSP has no `script-src`**, because pinning the pages' inline scripts needs a nonce per response and we
   cannot check one without a browser (V14.4.3). The API's CSP is complete. TLS itself is Render's edge and we have not tested it.
3. **Operators have no MFA.** Keys are named and static, held in the environment, rotated by hand (V4.3.1). The admin
   role is one shared read-only key.
4. **The jury deployment runs with `DEMO_MODE=1`** (`render.yaml`), so the demo-only routes, including the one that
   hands out test PINs, exist there. They answer 404 everywhere else. It also runs with `DEMO_CONSOLE=1`, so anyone can act
   as the bank on the cases their own sandbox session filed (gap 10).
5. **The team's console keys sit in a tracked file of the private repository** (`CLAVES_CONSOLA.md`). The public export
   removes it from every commit, and the keys must be rotated if access to the private repository ever widens.
6. **CSRF on the customer's web login and chat has no token and no check of our own** (V4.2.2). It rests on `SameSite=Lax` and on the framework's CSRF middleware, which `web/src/start.ts` registers for every server function and which answers 403 to a cross-site call. `web/src/start.test.ts` pins that it is registered and `web/tests/http/csrf-customer.test.ts` that the sign-in function answers 403, so an upgrade or a change to the start instance that dropped it would be caught. The rules are the framework's: for instance, it lets a call through when `Sec-Fetch-Site` says `same-origin` whatever `Origin` says, which a browser never sends. The operator's decisions and forms add our own origin check, which is stricter.
7. **State is single-process**: sessions, rate limits and conversations live in one SQLite file and one process
   (`LIMITATIONS.md`).
8. **No self-service data export or removal, and no privacy notice** in the web (V8.3.2, V8.3.3).
9. **Traces and tickets keep customer data**, with no redaction before they are exported anywhere (V7.1.2). Also, when the lookup of a customer's recent activity fails while a ticket is filed, the ticket's evidence note keeps the exception's text, not only its type (`agent/policy/escalation.py`); the fix is a separate change.
10. **The demo's console trusts the public sandbox accounts' design, not a person.** Their PINs are published, so the
    console's only barrier between visitors is the session: a visitor can never reach another's case, but anyone can sign in
    and decide their own, and so write up to 500 characters that their own session reads back as "Mensaje del agente". The
    visitor's words are sanitized as an operator's (one line, card numbers masked, no «») and always follow a fixed result of
    the case's family, but they are not reviewed. What visitors share on a public account is still shared: the per-account
    rate limits, the trace of a movement (one per customer and movement), and the trace reset of the "pending transfer"
    scenario, which clears it for every visitor. A case a visitor claims and leaves stays claimed by `demo` in the team's
    console until the retention purge. Signing in again is a new session, which no longer sees the earlier cases.

## What this document does not show

It is written from our own code, so it can be wrong where we misread it, and an "implemented" row means a control
exists and a test or file shows it, not that it has resisted an attacker.
