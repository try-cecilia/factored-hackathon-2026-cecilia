# Operator screen: cases walked and their result

The operator screen is the console in `web/src/routes/-operator/`, which talks to the `/admin/*` routes of `api/`.
This document lists what an operator can see and do there, which automated test covers each case, and what has **not**
been walked at all. Run on 2026-09-30, Windows 11, on the code of `feat/ablation` (`403f9e1`).

These are component and API tests. On 2026-09-30 the screen was also driven in a browser, by keyboard, on the deployed
demo (see [Walked on the deployed demo](#walked-on-the-deployed-demo-2026-09-30)).

## Results of the runs

| Suite | Command | Result |
|---|---|---|
| API, operator and desk (5 files) | `pytest tests/test_desk.py tests/test_operator_auth.py tests/test_access_matrix.py tests/test_human_queue.py tests/test_operator_codes.py` | 217 passed |
| Console components (jsdom) | `pnpm run test:dom` in `web/` | 149 passed, 18 files |
| Server and cookies, over the built app | `pnpm run test:http` in `web/` | 114 passed |
| Pure logic (`node --test`) | `pnpm run test` in `web/` | 198 passed, after fixing two Windows path bugs in the tests (below) |

**Two tests failed at first, and it was the tests' fault, not the product's.** Both built paths with `/` in a regex or
from `new URL(..).pathname`, which breaks on Windows. Fixed by normalizing the separator:
- `src/server/keys-stay-on-server.test.ts` crashed with `scandir 'C:\C:\Users\...'` before it checked anything. This is
  the guard that no client file of the console reads or sends the operator's key. It ran for the first time on this
  machine after the fix, and passes.
- `src/i18n/areas.test.ts` did not exclude `\i18n\context.tsx` on Windows, and read the example `t('shell.signOut')`
  in its doc comment as a key of the operator login.

Not re-run on Linux; the fix only normalizes separators, so it should behave the same there.

## Cases

| # | What the operator does or sees | Covered by | Result |
|---|---|---|---|
| 1 | Reads the queue: pending first, by priority, then oldest; closed work last | `queue.test.ts` (default order, stable sort, missing priority) | pass |
| 2 | Filters by queue, priority, country, language; searches by id, request, queue, operator; filters survive the URL | `queue.test.ts` | pass |
| 3 | Sees views "mine" and "unassigned", status tabs and counts | `queue.test.ts` | pass |
| 4 | A page past the end returns to the last one, with its rows | `queue.test.ts`, `Paging.dom.test.tsx` | pass |
| 5 | An old open case is still in the queue past the latest 200 | `test_human_queue.py` | pass |
| 6 | A corrupt line in the queue file is skipped and counted, without its content | `test_human_queue.py` | pass |
| 7 | Sees a case's language and country; a case without language is marked, not made up | `LocaleCell.dom.test.tsx`, `queue.test.ts` | pass |
| 8 | Reads the case in Spanish or Portuguese from the codes; an unknown code falls back to the English text | `TicketPanel.dom.test.tsx` | pass |
| 9 | Claims a case; a read-only session cannot and is asked for an operator key | `TicketPanel.dom.test.tsx`, `test_desk.py` | pass |
| 10 | Approves, rejects or releases with the version on screen | `TicketPanel.dom.test.tsx`, `test_desk.py` | pass |
| 11 | Approving twice, or retrying, never opens a second trace | `test_desk.py` | pass |
| 12 | Approving after the movement settled opens nothing, and says so | `test_desk.py`, `TicketPanel.dom.test.tsx` | pass |
| 13 | A decision needs the claim; a stale screen or another operator is refused | `test_desk.py` | pass |
| 14 | On a stale version the API answers 409 and the screen locks the decision and offers a reload | `test_desk.py`, `TicketPanel.dom.test.tsx`, `TicketRoute.dom.test.tsx` | pass |
| 15 | A reload that fails or throws keeps the lock and says so | `TicketPanel.dom.test.tsx`, `TicketRoute.dom.test.tsx` | pass |
| 16 | Resolves a case with no action, with a message for the customer; repeating changes nothing, other words are refused | `test_desk.py`, `TicketPanel.dom.test.tsx` | pass |
| 17 | The message to the customer is one line and never carries a full card number | `test_desk.py` | pass |
| 18 | The customer hears once what a person did; it survives a restart | `test_desk.py` | pass |
| 19 | The name recorded is the one of the key presented, never one sent in the body | `test_operator_auth.py` | pass |
| 20 | The admin key cannot act and the operator key cannot read | `test_operator_auth.py`, `test_access_matrix.py` | pass |
| 21 | Without operator keys, the action endpoints are off | `test_operator_auth.py` | pass |
| 22 | Too many failures from one origin give 429; the attempt is audited without the key | `test_operator_auth.py` | pass |
| 23 | Every route has a row in the access matrix and the matrix matches the docs | `test_access_matrix.py` | pass |
| 24 | Keys travel in cookies set by the server and never reach client code | `cookies-operator.test.ts`, `csrf.test.ts`; static guard `keys-stay-on-server.test.ts` | pass |

## Walked on the deployed demo (2026-09-30)

Chromium (Playwright 1.63, headless) against https://cecil-ai.onrender.com, from 22:04 to 22:09 (UTC-3), after the
red team session had closed, so none of its tickets was touched. On the console every control was reached with Tab or
Shift+Tab and pressed with Enter; no mouse. Sandbox customers filed four cases for the walk (their test PINs derived
with the read key), and after each decision the customer wrote again to see what a person did. Operator: `lautaro`.
The script stays outside the repository, because it needs the deploy's keys.

| Step | Result |
|---|---|
| Sign in with the read key and the operator key | pass: 2, 1 and 1 Tab presses, with a visible focus ring on both fields and the button |
| Take a case | pass, but it takes **64 Tab presses** from the top of the case page: the navigation and the queue come first, and there is no skip link |
| Approve a trace (`trace_review`, a transfer pending for 118 days) | pass: 1 Tab press after taking it. The customer's next message got "Ya tienes abierto el pedido de rastreo TR-D4A335369B5A709A ..." |
| Reject a trace, with a reason | pass: 3 Tab presses. The customer got "un agente lo revisó y no pudo abrir el rastreo ..." |
| Resolve a handoff (a stolen card), with a message | pass: 2 Tab presses. The customer got «Bloqueamos la tarjeta y te llamamos al número registrado.» |
| Hand a case back to the assistant | pass: 1 Tab press. The customer got "un agente lo devolvió al asistente" |
| A second screen of the same case, opened before the claim, tries to take it | pass: it locks the decision and offers "Recargar caso" |
| The queue at 390 px wide | pass: no sideways scroll |
| Accessible names | pass: every control was found by its role and its visible name |

On the customer's side, the proposal's "Sí, rastrear" button was 2 Tab presses away.

## Not walked

- **A screen reader.** The walk checked roles and names, not what a reader announces or in what order.
- **Two different operators at once.** The stale-screen lock was walked with one operator in two tabs. The API
  refuses a second operator (case 13).
- **Other browsers and a real phone.** Only Chromium; the phone width was emulated.
- **Load on the queue** beyond the retention cases above.
