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
  (15 idle minutes) minted only after a credential check.
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
| Model never decides or acts; replies are templates or verified facts | Implemented | ADR-001, `agent/core/render.py` |
| One confirmed action, idempotent, read back | Implemented | ADR-002, `api/idempotency.py` |
| Masking of customer text before a model | Implemented, with known holes | `agent/llm/privacy.py`, `LIMITATIONS.md` |
| Input limits: field schemas, 16 KiB body cap, per-session, customer and address rate limits, bounded concurrency | Implemented, per process | `api/main.py`, `api/middleware.py`, `tests/test_capacity.py` |
| API headers: CSP, `nosniff`, no framing, no referrer, `no-store`; CORS off by default, wildcard refused | Implemented | `api/security.py`, `tests/test_security.py` |
| Session cookie: `httpOnly`, `SameSite=Lax`, `Secure` and `__Host-` on https | Implemented | `web/src/server/cookie-policy.ts` |
| Origin check on operator form posts | Implemented | `web/src/server/origin-check.ts` |
| Web headers: `nosniff`, no framing, referrer policy, a CSP without `script-src`, HSTS on an https origin | Implemented, CSP partial | `web/serve.mjs`, `web/tests/http/serve.test.ts` |
| Tool audit, traces, tickets with a one-way session reference; retention loop that audits itself | Implemented; the records still hold customer data | `ops/retention.py`, `docs/operations.md` |
| Containers run unprivileged (API drops to `agent` with `setpriv`; web runs as `web`) | Implemented | `ops/entrypoint.sh`, `ops/Dockerfile.web` |
| Dependencies pinned with hashes | Implemented | `requirements.txt`, `pnpm-lock.yaml`, `make lock-check` |
| Dependency vulnerability scanning: `pip-audit` and `pnpm audit` fail the build on a known vulnerability | Implemented; no update bot | `.github/workflows/ci.yml` (`audit`) |
| Secret scanning | Partial: every blob is scanned when the public repository is exported, not in CI | `ops/export_public.py` |
| CI actions pinned by commit SHA | Implemented | `.github/workflows/ci.yml` |
| Red-team of the assistant (injection, other customers' ids, unauthorized access) | Done, on the assistant only | `tests/test_red_team.py`, `docs/red_team.md` |
| Penetration test, TLS and header test of the live deployment | **Not done** | |

## Known gaps

1. **No secret scanning in CI** (V14.2.1 is met for dependencies only). Secrets are scanned only at the public export.
2. **The web server's CSP has no `script-src`**, because pinning the pages' inline scripts needs a nonce per response and we
   cannot check one without a browser (V14.4.3). The API's CSP is complete. TLS itself is Render's edge and we have not tested it.
3. **Operators have no MFA.** Keys are named and static, held in the environment, rotated by hand (V4.3.1). The admin
   role is one shared read-only key.
4. **The jury deployment runs with `DEMO_MODE=1`** (`render.yaml`), so the demo-only routes, including the one that
   hands out test PINs, exist there. They answer 404 everywhere else.
5. **The team's console keys sit in a tracked file of the private repository** (`CLAVES_CONSOLA.md`). The public export
   removes it from every commit, and the keys must be rotated if access to the private repository ever widens.
6. **The intent model is a pickle** (`joblib`) committed to the repository and loaded without an integrity check
   (V5.5.3). It is never loaded from user input.
7. **CSRF on the customer's web login and chat rests on `SameSite=Lax`** alone (V4.2.2).
8. **State is single-process**: sessions, rate limits and conversations live in one SQLite file and one process
   (`LIMITATIONS.md`).
9. **No self-service data export or removal, and no privacy notice** in the web (V8.3.2, V8.3.3).
10. **Traces and tickets keep customer data**, with no redaction before they are exported anywhere (V7.1.2).

## What this document does not show

It is written from our own code, so it can be wrong where we misread it, and an "implemented" row means a control
exists and a test or file shows it, not that it has resisted an attacker.
