// F6: the operator's decisions (claim, approve, reject, release, resolve) are server-function POSTs, with no form to carry the origin
// check of the operator forms. They answer to the same check (origin-check.ts) as an explicit middleware of their own, on top of the
// CSRF middleware the app registers for every server function (src/start.ts). This pins it on the real `actOnTicket` of the build,
// with a session that holds an operator key, so a change that dropped either would let a foreign page act as the operator and fail
// here. SameSite=Strict on the cookie does not cover a sibling subdomain, which is the `same-site` case below. The pair
// Origin: foreign + Sec-Fetch-Site: same-origin cannot come from a browser; the framework's middleware alone lets it through, ours
// does not (the forms refuse it too, see csrf.test.ts).
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, ANA, ORIGIN, SAME_ORIGIN, sessionCookie, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
let cookie: string
before(async () => {
  app = await startConsole()
  cookie = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN, operator_key: ANA }, headers: SAME_ORIGIN }))!
})
after(() => app.close())

const ACTIONS = ['claim', 'approve', 'reject', 'release', 'resolve'] as const
const dataFor = (action: (typeof ACTIONS)[number]) => ({ ticket_id: 'TKT-0001-ABCD', action, expected_version: 1, reason: 'because', message: 'We solved it.' })
const decisionsAtTheDesk = () => app.requests.filter((r) => r.method === 'POST' && /^\/admin\/tickets\//.test(r.url))

const refused: [string, Record<string, string>][] = [
  ['cross-site', { 'Sec-Fetch-Site': 'cross-site' }],
  ['same-site (a sibling subdomain)', { 'Sec-Fetch-Site': 'same-site' }],
  ['none', { 'Sec-Fetch-Site': 'none' }],
  ['a foreign Origin', { Origin: 'https://attacker.invalid' }],
  ['Origin: null', { Origin: 'null' }],
  ['a foreign Origin that says same-origin', { Origin: 'https://attacker.invalid', 'Sec-Fetch-Site': 'same-origin' }],
  ['no signal at all', {}],
]

describe('a decision on a ticket that does not come from the console\'s own page', () => {
  for (const action of ACTIONS) {
    test(`${action}: every foreign or unproven call is a 403 with no cookie change and nothing sent to the desk`, async () => {
      for (const [label, proof] of refused) {
        const before = decisionsAtTheDesk().length
        const res = await app.rpc('actOnTicket', { data: dataFor(action), proof, headers: { Cookie: cookie } })
        assert.equal(res.status, 403, label)
        assert.deepEqual(res.headers.getSetCookie(), [], label)
        assert.equal(decisionsAtTheDesk().length, before, `${label} reached the desk`)
      }
    })

    test(`${action}: the same call from the console's own page reaches the desk with the operator's key`, async () => {
      const before = decisionsAtTheDesk().length
      const res = await app.rpc('actOnTicket', { data: dataFor(action), proof: { Origin: ORIGIN, 'Sec-Fetch-Site': 'same-origin' }, headers: { Cookie: cookie } })
      assert.equal(res.status, 200)
      const reached = decisionsAtTheDesk().slice(before)
      assert.equal(reached.length, 1)
      assert.equal(reached[0].url, `/admin/tickets/TKT-0001-ABCD/${action}`)
      assert.equal(reached[0].operator, ANA)
    })
  }
})
