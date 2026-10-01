import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { after, before, beforeEach, describe, test } from 'node:test'
import { toJSONAsync } from 'seroval'
import { ADMIN, opensConsole, SAME_ORIGIN, sessionCookie, startConsole } from './harness.ts'

// The console reads the customer's context through a server function (`loadCustomerContext`), called by the browser as
// GET /_serverFn/<id>?payload=<seroval>. Here it is called that way against the production build, in front of a fake API that answers
// with fields the console must never pass on.

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())
beforeEach(() => {
  app.setApi('ok')
  app.requests.length = 0
})

/** The id the build gave the function: the browser reads it from its own bundle; here it is read from the server's. */
const assets = join(import.meta.dirname, '../../dist/server/assets')
const functionId = readdirSync(assets)
  .filter((file) => file.endsWith('.js'))
  .map((file) => /id: "([0-9a-f]+)",\s*name: "loadCustomerContext"/.exec(readFileSync(join(assets, file), 'utf8'))?.[1])
  .find(Boolean)

const CANARIES = ['FULL-NUMBER-CANARY', 'EMAIL-CANARY', 'CHANNEL-CANARY', 'FRAUD-CANARY', 'DOCUMENT-CANARY', '1234567890123456']
const fromApi = {
  warehouse: { available: true, as_of: '2026-09-29' },
  products: [{ product_id: 'p1', type: 'Cuenta Ahorro', currency: 'USD', status: 'Active', last4: '1234567890123456', product_number: 'FULL-NUMBER-CANARY', email: 'EMAIL-CANARY' }],
  movements: [{ transaction_id: 't1', date: '2026-09-28T10:00:00', product_id: 'p1', type: 'Transfer', amount: 40, currency: 'USD', merchant: null, status: 'Pending', pending: true, channel: 'CHANNEL-CANARY', fraud_score: 'FRAUD-CANARY' }],
  pending_omitted: 0,
  cases: [],
  traces: [],
  document_number: 'DOCUMENT-CANARY',
}

const login = (cookie?: string) => app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: { ...SAME_ORIGIN, ...(cookie && { Cookie: cookie }) } })
const touchesSession = (response: Response) => response.headers.getSetCookie().some((c) => /cecilai_operator=/.test(c) && !/flash/.test(c))

async function readContext(cookie: string | undefined, ticketId = 'ticket-123', headers: Record<string, string> = SAME_ORIGIN) {
  const payload = JSON.stringify(await toJSONAsync({ data: { ticket_id: ticketId }, context: {} }))
  return app.send(`/_serverFn/${functionId}?payload=${encodeURIComponent(payload)}`, {
    headers: { ...headers, 'x-tsr-serverFn': 'true', Accept: 'application/json', ...(cookie && { Cookie: cookie }) },
  })
}
const contextRequests = () => app.requests.filter((r) => r.url.includes('/customer_context'))

describe('the customer context through the BFF', () => {
  test('the build has the function', () => assert.ok(functionId, 'loadCustomerContext is not in the production build'))

  test('without a session nothing is asked of the API', async () => {
    const res = await readContext(undefined)
    assert.match(await res.text(), /status/)
    assert.equal(contextRequests().length, 0)
  })

  test('it reads with the session\'s read key, never the operator key, and only a fixed set of fields reaches the browser', async () => {
    const cookie = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN, operator_key: 'ana-key-0123456789-abcdefghij' }, headers: SAME_ORIGIN }))!
    app.setContext({ body: fromApi })
    const res = await readContext(cookie)
    const body = await res.text()
    assert.equal(res.status, 200)
    assert.ok(body.includes('warehouse') && body.includes('p1') && body.includes('t1'), body)
    for (const canary of [...CANARIES, ADMIN]) assert.ok(!body.includes(canary), `the response carries ${canary}`)
    assert.equal(contextRequests().at(-1)?.admin, ADMIN)
    assert.equal(contextRequests().at(-1)?.operator, undefined)
    assert.equal(contextRequests().at(-1)?.url, '/admin/tickets/ticket-123/customer_context')
  })

  test('an id that is not a case id never reaches the API', async () => {
    const cookie = sessionCookie(await login())!
    app.setContext({ body: fromApi })
    await (await readContext(cookie, '../../../admin/x')).text()
    assert.equal(contextRequests().length, 0)
  })

  test('a request that does not come from the console\'s own origin is refused', async () => {
    const cookie = sessionCookie(await login())!
    const res = await readContext(cookie, 'ticket-123', {})
    assert.equal(res.status, 403)
    assert.equal(contextRequests().length, 0)
  })

  test('a body that is not the contract is a 502 of this section, and the session lives', async () => {
    const cookie = sessionCookie(await login())!
    app.setContext({ body: { nothing: 'useful' } })
    assert.match(await (await readContext(cookie)).text(), /502/)
    assert.ok(await opensConsole(app, cookie))
  })

  test('a 401 ends the session that asked without a Set-Cookie, and a late 401 cannot delete the new login', async () => {
    const old = sessionCookie(await login())!
    app.setContext({ status: 401 })
    const revoked = await readContext(old)
    await revoked.text()
    assert.equal(touchesSession(revoked), false)
    assert.equal(await opensConsole(app, old), false, 'the session is gone on the server')

    app.setContext({ status: 200, body: fromApi })
    const first = sessionCookie(await login())!
    const slow = app.holdContext()
    const pendingRead = readContext(first) // waits inside the API
    await slow.reached
    const replaced = sessionCookie(await login(first))! // a new login takes over while the read is pending
    slow.release(401)
    const late = await pendingRead
    await late.text()
    assert.equal(touchesSession(late), false, late.headers.getSetCookie().join(' | '))
    assert.ok(await opensConsole(app, replaced), 'the new session is still alive')
  })
})
