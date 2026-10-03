// The one-click demo against the production build, in front of a fake API in demo mode: the entry (enterDemo) and the bank's side
// (/demo/desk/*). A server function is a public URL, so what holds here is what holds for a direct call: the switches are fail-closed
// (DEMO_MODE and DEMO_CONSOLE exactly '1'), the decisions and the entry come only from the app's own page, the entry is limited per
// address, the PIN stays on the server, and the bank's side carries the customer's session and never an operator key.
import assert from 'node:assert/strict'
import type { IncomingMessage } from 'node:http'
import { after, before, beforeEach, describe, test } from 'node:test'
import { ORIGIN, startCustomerApp, TOKEN } from './customer-harness.ts'
import { rpcOutcome } from './rpc.ts'

const PIN = '424242'
const PT_PIN = '515151'
const scenario = (id: string, customer_id: string, test_pin: string, language = 'es', fault: string | null = null) => ({
  id, path: 'normal', customer_id, language, fault, turns: ['hola'], expect: [null], test_pin,
  title: { en: 'x', es: 'x' }, look_for: { en: 'x', es: 'x' },
})
const scenarios = [
  scenario('normal_balance', 'CLI-FIX0001', PIN),
  scenario('action_trace', 'CLI-FIX0003', PIN, 'es', 'clear_traces'),
  scenario('normal_pt_arrears', 'CLI-FIX0005', PT_PIN, 'pt'),
]
let publicIds = ['CLI-FIX0001', 'CLI-FIX0003', 'CLI-FIX0005']
const TICKET = 'b99d8390-4d20-4fd1-83d0-e435cb825b63'
const desk = (status: string, operator: string | null, version: number) => ({ ticket_id: TICKET, status, operator, trace_id: null, version, history: operator ? [{ action: 'claim', status: 'claimed', operator, ts: 1, detail: {} }] : [] })
const ticket = (operator: string | null = null) => ({
  ticket_id: TICKET, trace_id: 't1', created_at: 1, category: 'fraud', priority: 'Critical', queue: 'fraud_ops', customer_id: 'CLI-FIX0001',
  session_ref: 'ref-1', segment: 'Premium', country: 'México', language: 'es', request: 'No reconozco un cargo', prior_requests: [], reason: 'r',
  policy_rule: 'lexicon', verified_facts: [], evidence: [], actions_taken: [], open_questions: [], suggested_next_step: 's', pending_action: null,
  desk: desk(operator ? 'claimed' : 'open', operator, operator ? 1 : 0), resolve_results: ['charge_confirmed', 'will_contact', 'Not A Code', 'call_the_bank'],
})

// Every request the fake's own part saw (the harness answers /auth/session itself and lists it in app.seen), with its headers and body.
const heard: { url: string; method: string; token?: string; admin?: string; operatorKey?: string; body: string }[] = []
// What the desk answers next: a status and a body, or the default.
let deskAnswer: { status: number; body: unknown } | null = null

function fake(req: IncomingMessage, reply: (status: number, body: unknown) => void) {
  const url = req.url ?? ''
  if (url === '/demo/scenarios') return reply(200, scenarios)
  if (url === '/demo/customers') return reply(200, publicIds.map((customer_id) => ({ customer_id, test_pin: PIN })))
  if (url === '/demo/fault') return reply(200, { ok: true })
  if (url === '/demo/traces' || url === '/demo/tickets') return reply(200, [])
  if (!url.startsWith('/demo/desk/')) return false
  if (deskAnswer) return reply(deskAnswer.status, deskAnswer.body)
  if (url === '/demo/desk/tickets') return reply(200, [ticket('ana')])
  if (url === `/demo/desk/tickets/${TICKET}`) return reply(200, ticket('ana'))
  if (url === `/demo/desk/tickets/${TICKET}/customer_context`) return reply(200, { warehouse: { available: false, as_of: null }, products: [], movements: [], pending_omitted: 0, cases: [], traces: [] })
  const action = /^\/demo\/desk\/tickets\/[^/]+\/(claim|approve|reject|release|resolve)$/.exec(url)
  if (action && req.method === 'POST') return reply(200, { ...desk(action[1] === 'resolve' ? 'resolved' : 'claimed', 'demo', 2), result: action[1] === 'resolve' ? 'will_contact' : null })
  return reply(404, { detail: 'ticket not found' })
}

let app: Awaited<ReturnType<typeof startCustomerApp>>
before(async () => {
  app = await startCustomerApp((req, reply) => {
    let body = ''
    req.on('data', (chunk) => (body += chunk))
    const entry = { url: req.url ?? '', method: req.method ?? '', token: req.headers['x-session-token'] as string | undefined, admin: req.headers['x-admin-key'] as string | undefined, operatorKey: req.headers['x-operator-key'] as string | undefined, body: '' }
    heard.push(entry)
    req.on('end', () => (entry.body = body))
    return fake(req, reply)
  })
})
after(() => {
  for (const name of ['DEMO_MODE', 'DEMO_CONSOLE', 'DEMO_ENTER_RATE_PER_MIN', 'TRUSTED_CLIENT_IP_HEADER']) delete process.env[name]
  return app.close()
})

let ip = 0
// Each test enters from an address of its own, so the per-address limit of one test never refuses another's entry.
const fromNewAddress = () => ({ 'x-test-ip': `10.0.0.${++ip}` })
beforeEach(() => {
  heard.length = 0
  app.seen.length = 0
  deskAnswer = null
  publicIds = ['CLI-FIX0001', 'CLI-FIX0003', 'CLI-FIX0005']
  process.env.DEMO_MODE = '1'
  process.env.DEMO_CONSOLE = '1'
  process.env.TRUSTED_CLIENT_IP_HEADER = 'x-test-ip'
  delete process.env.DEMO_ENTER_RATE_PER_MIN
})

const session = { Cookie: `cecilai_session=${TOKEN}` }
const SAME = { Origin: ORIGIN, 'Sec-Fetch-Site': 'same-origin' }
const call = async (name: string, init: { method?: 'GET' | 'POST'; data?: unknown; headers?: Record<string, string>; proof?: Record<string, string> } = {}) => {
  const res = await app.rpc(name, { method: init.method ?? 'POST', data: init.data, headers: init.headers, proof: init.proof ?? SAME })
  return { res, ...(await rpcOutcome(res)) }
}
const toApi = (prefix: string) => [...heard, ...app.seen].filter((r) => r.url.startsWith(prefix))
const sessionCookieOf = (res: Response) => res.headers.getSetCookie().find((c) => /^cecilai_session=[^;]/.test(c))

const READS: [string, unknown][] = [['loadDemoQueue', undefined], ['loadDemoTicket', { ticket_id: TICKET }], ['loadDemoCustomerContext', { ticket_id: TICKET }]]

describe('fail-closed: without DEMO_MODE=1 and DEMO_CONSOLE=1, exactly, the demo console does not exist', () => {
  const off: [string, Record<string, string | undefined>][] = [
    ['DEMO_CONSOLE unset', { DEMO_MODE: '1', DEMO_CONSOLE: undefined }],
    ['DEMO_CONSOLE=0', { DEMO_MODE: '1', DEMO_CONSOLE: '0' }],
    ['DEMO_CONSOLE=true', { DEMO_MODE: '1', DEMO_CONSOLE: 'true' }],
    ['DEMO_MODE unset', { DEMO_MODE: undefined, DEMO_CONSOLE: '1' }],
    ['DEMO_MODE=0', { DEMO_MODE: '0', DEMO_CONSOLE: '1' }],
    ['DEMO_MODE=true', { DEMO_MODE: 'true', DEMO_CONSOLE: '1' }],
  ]
  for (const [label, env] of off) {
    test(`${label}: every function of it is an HTTP 404, a malformed payload too, and nothing reaches the API`, async () => {
      for (const [name, value] of Object.entries(env)) value === undefined ? delete process.env[name] : (process.env[name] = value)
      const calls: [string, 'GET' | 'POST', unknown][] = [
        ['enterDemo', 'POST', { role: 'cuentas' }],
        ['enterDemo', 'POST', { role: 'admin' }],
        ['getDemoDeskView', 'GET', undefined],
        ...READS.map(([name, data]): [string, 'GET', unknown] => [name, 'GET', data]),
        ['loadDemoTicket', 'GET', { ticket_id: '!' }],
        ['actOnDemoTicket', 'POST', { ticket_id: TICKET, action: 'claim' }],
        ['actOnDemoTicket', 'POST', { ticket_id: TICKET, action: 'close', expected_version: 'x' }],
      ]
      for (const [name, method, data] of calls) {
        const res = await app.rpc(name, { method, data, proof: SAME, headers: { ...session, ...fromNewAddress() } })
        assert.equal(res.status, 404, `${name} ${JSON.stringify(data)}`)
        assert.deepEqual(res.headers.getSetCookie(), [], name)
        await res.arrayBuffer()
      }
      assert.deepEqual(toApi('/auth/session'), [])
      assert.deepEqual(toApi('/demo/desk'), [])
      const kit = (await call('getDemoKit', { method: 'GET' })).result as { console?: boolean; entries?: unknown[] }
      assert.ok(kit.console !== true && !kit.entries?.length, JSON.stringify(kit))
      // The bank's side is not drawn: the page sends to the home page.
      const page = await app.get('/demo/banco', session)
      assert.equal(page.status, 307)
      assert.equal(new URL(page.headers.get('location') ?? '', ORIGIN).pathname, '/')
    })
  }
})

describe('entering the demo with one click', () => {
  test('signs in on the server as the role\'s customer: revokes the old session, sets the cookie, and the PIN never leaves', async () => {
    const entry = await call('enterDemo', { data: { role: 'cuentas' }, headers: { ...session, ...fromNewAddress() } })
    assert.deepEqual(entry.result, { ok: true, language: 'es' })
    const cookie = sessionCookieOf(entry.res)
    assert.ok(cookie, 'the session cookie is set')
    assert.match(cookie, /HttpOnly/i)
    assert.match(cookie, /SameSite=Lax/i)
    assert.match(cookie, /Max-Age=900/i)
    assert.ok(!entry.text.includes(PIN), 'the PIN is not in the answer')
    assert.ok(app.seen.some((r) => r.url === '/auth/session' && r.method === 'DELETE' && r.token === TOKEN), 'the previous session is revoked first')
    assert.ok(app.seen.some((r) => r.url === '/auth/session' && r.method === 'POST'), 'the server signed in')
    const kit = await call('getDemoKit', { method: 'GET' })
    assert.ok(!kit.text.includes(PIN) && !kit.text.includes(PT_PIN), 'the kit hands out no PIN')
    assert.deepEqual((kit.result as { entries: { role: string }[] }).entries.map((e) => e.role), ['cuentas', 'pendiente', 'portugues'])
  })

  test('the pending transfer starts with no earlier traces, and the Portuguese customer leaves the interface\'s language alone', async () => {
    await call('enterDemo', { data: { role: 'pendiente' }, headers: fromNewAddress() })
    assert.ok(heard.some((r) => r.url === '/demo/fault' && JSON.parse(r.body || '{}').fault === 'clear_traces'))
    const pt = await call('enterDemo', { data: { role: 'portugues' }, headers: fromNewAddress() })
    assert.deepEqual(pt.result, { ok: true, language: 'pt' })
    assert.ok(sessionCookieOf(pt.res), 'signed in as the Portuguese customer')
    assert.ok(!pt.res.headers.getSetCookie().some((c) => c.startsWith('cecilai_lang=')), 'only the language switcher sets the language')
    assert.ok(!pt.text.includes(PT_PIN))
  })

  test('entering again as the Portuguese customer, a different one from the accounts\' (CLI-FIX0005), keeps the interface in Spanish', async () => {
    const first = await call('enterDemo', { data: { role: 'portugues' }, headers: { Cookie: 'cecilai_lang=es', ...fromNewAddress() } })
    const cookie = sessionCookieOf(first.res)
    assert.ok(cookie)
    const before = app.seen.length
    const again = await call('enterDemo', { data: { role: 'portugues' }, headers: { Cookie: `${cookie.split(';')[0]}; cecilai_lang=es`, ...fromNewAddress() } })
    assert.deepEqual(again.result, { ok: true, language: 'pt' })
    assert.ok(app.seen.slice(before).some((r) => r.url === '/auth/session' && r.method === 'DELETE'), 'the expired session is revoked first')
    assert.ok(sessionCookieOf(again.res), 'a new session')
    assert.ok(!again.res.headers.getSetCookie().some((c) => c.startsWith('cecilai_lang=')), 'the language cookie is not touched')
  })

  test('an account the API no longer lists as public is not signed in with', async () => {
    publicIds = ['CLI-FIX0003']
    const entry = await call('enterDemo', { data: { role: 'cuentas' }, headers: fromNewAddress() })
    assert.deepEqual(entry.result, { ok: false, reason: 'failed' })
    assert.equal(sessionCookieOf(entry.res), undefined)
    assert.ok(!app.seen.some((r) => r.url === '/auth/session' && r.method === 'POST'))
  })

  test('a role that is not one of the three is refused before anything happens', async () => {
    const entry = await call('enterDemo', { data: { role: 'admin' }, headers: fromNewAddress() })
    assert.equal(entry.error, 'role is not valid')
    assert.deepEqual(toApi('/auth/session'), [])
  })

  test('is limited per address: past the limit, no login reaches the API, and another address still enters', async () => {
    process.env.DEMO_ENTER_RATE_PER_MIN = '2'
    const address = fromNewAddress()
    for (let i = 0; i < 2; i++) assert.equal((await call('enterDemo', { data: { role: 'cuentas' }, headers: address })).result && true, true)
    const logins = () => app.seen.filter((r) => r.url === '/auth/session' && r.method === 'POST').length
    const before = logins()
    const refused = await call('enterDemo', { data: { role: 'cuentas' }, headers: address })
    const outcome = refused.result as { ok: boolean; reason: string; retryAfter: number }
    assert.equal(outcome.ok, false)
    assert.equal(outcome.reason, 'limited')
    assert.ok(outcome.retryAfter >= 1 && outcome.retryAfter <= 60)
    assert.equal(logins(), before, 'the refused entry never reached the API')
    assert.equal(sessionCookieOf(refused.res), undefined)
    assert.deepEqual((await call('enterDemo', { data: { role: 'cuentas' }, headers: fromNewAddress() })).result, { ok: true, language: 'es' })
  })
})

describe('only from the app\'s own page: the origin check on top of the framework\'s CSRF middleware', () => {
  const refused: [string, Record<string, string>][] = [
    ['cross-site', { 'Sec-Fetch-Site': 'cross-site' }],
    ['same-site (a sibling subdomain)', { 'Sec-Fetch-Site': 'same-site' }],
    ['a foreign Origin', { Origin: 'https://attacker.invalid' }],
    ['Origin: null', { Origin: 'null' }],
    ['a foreign Origin that says same-origin', { Origin: 'https://attacker.invalid', 'Sec-Fetch-Site': 'same-origin' }],
    ['no signal at all', {}],
  ]
  const writes: [string, unknown][] = [
    ['enterDemo', { role: 'cuentas' }],
    ['actOnDemoTicket', { ticket_id: TICKET, action: 'resolve', result_code: 'will_contact', expected_version: 1 }],
    ['startScenario', { id: 'normal_balance' }],
  ]
  for (const [name, data] of writes) {
    test(`${name}: every foreign or unproven call is a 403 that changes no cookie and reaches nothing`, async () => {
      for (const [label, proof] of refused) {
        const res = await app.rpc(name, { data, proof, headers: { ...session, ...fromNewAddress() } })
        assert.equal(res.status, 403, `${name}, ${label}`)
        assert.deepEqual(res.headers.getSetCookie(), [], `${name}, ${label}`)
      }
      assert.deepEqual(toApi('/auth/session'), [])
      assert.deepEqual(toApi('/demo/'), [])
    })
  }

  test('a read of the bank\'s side from another site is refused by the framework', async () => {
    for (const [name, data] of READS) {
      const res = await app.rpc(name, { method: 'GET', data, proof: { 'Sec-Fetch-Site': 'cross-site' }, headers: session })
      assert.equal(res.status, 403, name)
    }
    assert.deepEqual(toApi('/demo/desk'), [])
  })
})

describe('the bank\'s side', () => {
  test('without a session it is the landing, where one click enters: no dialog, no entry link in the address', async () => {
    const page = await app.get('/demo/banco')
    assert.equal(page.status, 307)
    const to = new URL(page.headers.get('location') ?? '', ORIGIN)
    assert.equal(to.pathname, '/')
    assert.equal(to.search, '')
    await page.arrayBuffer()
  })

  test('carries the customer\'s session and no operator key, even with an operator\'s cookie in the same browser', async () => {
    const both = { Cookie: `cecilai_session=${TOKEN}; cecilai_operator=someone-elses-console-session` }
    for (const [name, data] of READS) await call(name, { method: 'GET', data, headers: both })
    await call('actOnDemoTicket', { data: { ticket_id: TICKET, action: 'claim', expected_version: 0 }, headers: both })
    const desk = heard.filter((r) => r.url.startsWith('/demo/desk'))
    assert.equal(desk.length, 4)
    for (const r of desk) {
      assert.equal(r.token, TOKEN, r.url)
      assert.equal(r.admin, undefined, r.url)
      assert.equal(r.operatorKey, undefined, r.url)
    }
  })

  test('the view says whose session it is and how long it has; without a cookie, or with one the API rejects, there is none', async () => {
    const view = (await call('getDemoDeskView', { method: 'GET', headers: session })).result
    assert.deepEqual(view, { status: 'active', customerId: 'CLI-FIX0001', sessionRef: 'ref-1', expiresIn: 900 })
    assert.deepEqual((await call('getDemoDeskView', { method: 'GET' })).result, { status: 'no_session' })
    const rejected = await call('getDemoDeskView', { method: 'GET', headers: { Cookie: 'cecilai_session=revoked-token' } })
    assert.deepEqual(rejected.result, { status: 'no_session' })
    assert.deepEqual(rejected.res.headers.getSetCookie(), [], 'a passive read leaves the cookie alone')
  })

  test('a case comes with its results and without the name of a person of the team', async () => {
    const read = await call('loadDemoTicket', { method: 'GET', data: { ticket_id: TICKET }, headers: session })
    const data = (read.result as { ok: true; data: { resolve_results: string[]; desk: { operator: string; history: { operator: string }[] } } }).data
    assert.deepEqual(data.resolve_results, ['charge_confirmed', 'will_contact', 'call_the_bank'])
    assert.equal(data.desk.operator, 'banco')
    assert.ok(!read.text.includes('"ana"') && !read.text.includes('ana'), 'the operator\'s name stays on the server')
    const queue = await call('loadDemoQueue', { method: 'GET', headers: session })
    assert.ok(!queue.text.includes('ana'))
  })

  test('a resolution sends the predefined result and the message, and nothing else', async () => {
    const res = await call('actOnDemoTicket', { data: { ticket_id: TICKET, action: 'resolve', expected_version: 1, result_code: 'will_contact', message: '  Ya hablamos.  ', operator: 'ana' }, headers: session })
    assert.equal((res.result as { ok: boolean }).ok, true)
    const sent = heard.find((r) => r.url === `/demo/desk/tickets/${TICKET}/resolve`)
    assert.deepEqual(JSON.parse(sent!.body), { expected_version: 1, result_code: 'will_contact', message: 'Ya hablamos.' })
    const missing = await call('actOnDemoTicket', { data: { ticket_id: TICKET, action: 'resolve', expected_version: 1, message: 'x' }, headers: session })
    assert.equal(missing.error, 'result_code is required to resolve')
  })

  test('the API\'s words reach the page only for a 400 or a 409; a 401 leaves the cookie, a 500 says only its status', async () => {
    deskAnswer = { status: 409, body: { detail: 'another person took this case' } }
    assert.deepEqual((await call('actOnDemoTicket', { data: { ticket_id: TICKET, action: 'claim', expected_version: 0 }, headers: session })).result, { ok: false, status: 409, message: 'another person took this case' })
    deskAnswer = { status: 500, body: { detail: 'Traceback: secret internals' } }
    const failed = await call('loadDemoQueue', { method: 'GET', headers: session })
    assert.deepEqual(failed.result, { ok: false, status: 500 })
    assert.ok(!failed.text.includes('secret internals'))
    for (const status of [401, 403, 404, 429]) {
      deskAnswer = { status, body: { detail: `detail of ${status}` } }
      const read = await call('loadDemoTicket', { method: 'GET', data: { ticket_id: TICKET }, headers: session })
      assert.deepEqual(read.result, { ok: false, status }, String(status))
      assert.deepEqual(read.res.headers.getSetCookie(), [], String(status))
    }
    deskAnswer = null
    assert.deepEqual((await call('loadDemoQueue', { method: 'GET' })).result, { ok: false, status: 0 }, 'no cookie, no call')
  })

  test('after "Salir", even with the API hanging, the bank\'s side has no session', async () => {
    app.setDelete('hang')
    try {
      const out = await call('logout', { headers: session })
      assert.ok(out.res.headers.getSetCookie().some((c) => /^cecilai_session=;|Max-Age=0/i.test(c)), 'the cookie is cleared')
      assert.deepEqual((await call('getDemoDeskView', { method: 'GET' })).result, { status: 'no_session' })
    } finally {
      app.setDelete('ok')
    }
  })
})
