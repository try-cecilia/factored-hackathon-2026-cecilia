# Operator screen: cases walked and their result

The operator screen is the console in `web/src/routes/-operator/`, which talks to the `/admin/*` routes of `api/`.
This document lists what an operator can see and do there, which automated test covers each case, and what has **not**
been walked at all. Run on 2026-09-30, Windows 11, on the code of `feat/ablation` (`403f9e1`).

These are component and API tests. Nobody has driven the screen in a real browser yet (see the last section).

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

## Not walked

- **No manual run in a browser.** Nobody has done queue, claim, approve, and then the customer seeing the news, on the
  local demo. The component tests do not show layout, focus or what the screen looks like on a phone.
- **No screen-reader or keyboard pass** on the console.
- **No test of two operators on the screen at once.** The API refuses the second one (case 13); how the losing
  screen looks is covered only by the 409 lock in the component test.
- **Load on the queue** beyond the retention cases above.
