// The demo's server functions against the production build, in front of a fake API that stays in demo mode. A server function
// is a public URL: hiding the panel stops no one, so the web's own DEMO_MODE=0 and the API's list of public accounts have to
// hold for a direct call (the report of the security review, F4).
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { after, before, beforeEach, describe, test } from 'node:test'
import { toJSONAsync } from 'seroval'
import { ORIGIN, startCustomerApp, TOKEN } from './customer-harness.ts'

const scenario = (id: string, customer_id: string, test_pin: string) => ({
  id, path: 'normal', customer_id, language: 'es', fault: null, turns: ['hola'], expect: [null], test_pin,
  title: { en: 'Balance', es: 'Consulta de saldo' }, look_for: { en: 'x', es: 'y' },
})
const PUBLIC_PIN = '111111'
const OTHER_PIN = '999999'
const scenarios = [scenario('public_one', 'CLI-FIX0001', PUBLIC_PIN), scenario('stale_one', 'CLI-FIX0009', OTHER_PIN)]
// What the API lists as public now: the second scenario's account is not on it (a list changed after the scenarios were read).
const customers = [{ customer_id: 'CLI-FIX0001', test_pin: PUBLIC_PIN }]

let app: Awaited<ReturnType<typeof startCustomerApp>>
let handler: { fetch(request: Request): Promise<Response> }
before(async () => {
  app = await startCustomerApp((req, reply) => {
    if (req.url === '/demo/scenarios') return reply(200, scenarios)
    if (req.url === '/demo/customers') return reply(200, customers)
    if (req.url === '/demo/fault' || req.url === '/demo/tickets' || req.url === '/demo/traces') return reply(200, [])
    return false
  })
  // The harness has set AGENT_API_URL and the origin; this is the same module instance it loaded.
  handler = (await import(pathToFileURL(join(import.meta.dirname, '../../dist/server/server.js')).href)).default
})
after(() => {
  delete process.env.DEMO_MODE
  return app.close()
})
beforeEach(() => {
  app.seen.length = 0
  delete process.env.DEMO_MODE
})

const assets = join(import.meta.dirname, '../../dist/server/assets')
const files = readdirSync(assets).filter((file) => file.endsWith('.js'))
/** The id the build gave a server function: the browser reads it from its bundle; here from the server's. */
const functionId = (name: string) =>
  files.map((file) => new RegExp(`id: "([0-9a-f]+)",\\s*name: "${name}"`).exec(readFileSync(join(assets, file), 'utf8'))?.[1]).find(Boolean)

const SAME_SITE = { Origin: ORIGIN, 'Sec-Fetch-Site': 'same-origin' }
async function call(name: string, method: 'GET' | 'POST', data: unknown, cookie?: string) {
  const id = functionId(name)
  assert.ok(id, `${name} is in the production build`)
  const payload = JSON.stringify(await toJSONAsync({ data, context: {} }))
  const headers = { ...SAME_SITE, 'x-tsr-serverFn': 'true', Accept: 'application/json', ...(cookie && { Cookie: cookie }) }
  const request =
    method === 'GET'
      ? new Request(`${ORIGIN}/_serverFn/${id}?payload=${encodeURIComponent(payload)}`, { headers })
      : new Request(`${ORIGIN}/_serverFn/${id}`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: payload })
  return handler.fetch(request)
}
const asked = () => app.seen.map((r) => r.url).filter((url) => url.startsWith('/demo/') || url === '/auth/session')
const signsIn = (res: Response) => res.headers.getSetCookie().some((c) => /cecilai_session=[^;]/.test(c))
const session = `cecilai_session=${TOKEN}`

describe('with DEMO_MODE=0 on the web and the API still in demo mode', () => {
  beforeEach(() => void (process.env.DEMO_MODE = '0'))

  test('startScenario signs nobody in, sets no cookie and asks the API for nothing', async () => {
    const res = await call('startScenario', 'POST', { id: 'public_one' })
    assert.ok(!signsIn(res))
    assert.deepEqual(res.headers.getSetCookie(), [])
    assert.deepEqual(asked(), [])
    const body = await res.text()
    assert.ok(!body.includes(PUBLIC_PIN) && !body.includes('"ok":true') && !body.includes('ok:!0'), body)
  })

  test('applyDemoFault, the bank view and the traces do nothing, even with a live session', async () => {
    for (const [name, method, data] of [
      ['applyDemoFault', 'POST', { fault: 'llm_outage' }],
      ['getDemoTickets', 'GET', undefined],
      ['getDemoTraces', 'GET', undefined],
    ] as const) {
      const res = await call(name, method, data, session)
      assert.deepEqual(res.headers.getSetCookie(), [], name)
    }
    assert.deepEqual(asked(), [])
  })

  test('getDemoCustomers and getDemoKit hand out no PIN and ask the API for nothing', async () => {
    for (const name of ['getDemoCustomers', 'getDemoKit']) {
      const body = await (await call(name, 'GET', undefined)).text()
      assert.ok(!body.includes(PUBLIC_PIN) && !body.includes('CLI-FIX0001'), `${name}: ${body}`)
    }
    assert.deepEqual(asked(), [])
  })
})

describe('with the demo on', () => {
  test('a scenario of a public account starts: it signs in and sets the session cookie', async () => {
    const res = await call('startScenario', 'POST', { id: 'public_one' })
    assert.ok(signsIn(res))
    assert.ok(!(await res.text()).includes(PUBLIC_PIN), 'the sandbox PIN stays on the server')
  })

  test('a scenario whose account the API no longer lists as public is not started', async () => {
    const res = await call('startScenario', 'POST', { id: 'stale_one' })
    assert.ok(!signsIn(res))
    assert.deepEqual(res.headers.getSetCookie(), [])
    assert.ok(!app.seen.some((r) => r.url === '/auth/session'), 'no login was attempted')
  })
})
