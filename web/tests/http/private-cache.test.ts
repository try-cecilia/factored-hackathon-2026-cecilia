// F2: what the BFF answers with data of a person is not for any cache to keep: the pages (they carry the session and the conversation in
// their data), the server functions (tickets, context, history), the errors and the redirects. serve.mjs sets the policy on everything
// the app answers, whatever the app says; the build's hashed files stay public and immutable. A process of serve.mjs in front of a fake API.
import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { readdirSync } from 'node:fs'
import { createServer, type IncomingMessage, type Server } from 'node:http'
import { createServer as netServer, type AddressInfo } from 'node:net'
import { join } from 'node:path'
import { after, before, describe, test } from 'node:test'
import { rpcRequest } from './rpc.ts'

const web = join(import.meta.dirname, '../..')
const ADMIN = 'admin-key-0123456789-abcdefgh'
const ANA = 'ana-key-0123456789-abcdefghij'
const TOKEN = 'tok-cache-0123456789abcdef'
const session = { customer_id: 'CLI-FIX0001', session_ref: 'ref-1', segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }
const turns = [{ role: 'user', text: 'Mi saldo', at: 1_760_000_000 }]

let api: Server
let server: ChildProcess
let base = ''
let operator = ''

const freePort = () =>
  new Promise<number>((done) => {
    const probe = netServer().listen(0, '127.0.0.1', () => {
      const { port } = probe.address() as AddressInfo
      probe.close(() => done(port))
    })
  })

function fakeApi(req: IncomingMessage, reply: (status: number, body: unknown) => void) {
  const admin = req.headers['x-admin-key'] === ADMIN
  const op = req.headers['x-operator-key'] === ANA
  if (req.url === '/auth/session' && req.method === 'POST') return reply(200, { token: TOKEN, expires_in: 900 })
  if (req.url === '/auth/session') return req.headers['x-session-token'] === TOKEN ? reply(200, session) : reply(401, { detail: 'invalid or expired session' })
  if (req.url === '/chat/history') return reply(200, { turns, cases: [] })
  if (req.url?.startsWith('/admin/operator/me')) return op ? reply(200, { operator: 'ana' }) : reply(401, { detail: 'invalid operator key' })
  if (req.url?.startsWith('/admin/')) return admin ? reply(200, req.url.startsWith('/admin/human_queue') ? [] : req.url.includes('/customer_context') ? {} : {}) : reply(401, { detail: 'invalid admin key' })
  return reply(404, { detail: 'Not Found' })
}

before(async () => {
  api = createServer((req, res) => fakeApi(req, (status, body) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)) }))
  await new Promise<void>((done) => api.listen(0, '127.0.0.1', done))
  const port = await freePort()
  base = `http://127.0.0.1:${port}`
  server = spawn(process.execPath, ['serve.mjs'], {
    cwd: web,
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', NODE_ENV: 'production', WEB_PUBLIC_ORIGIN: base, AGENT_API_URL: `http://127.0.0.1:${(api.address() as AddressInfo).port}` },
    stdio: 'ignore',
  })
  for (let i = 0; i < 100; i++) {
    if (await fetch(`${base}/_healthz`).then((r) => r.ok, () => false)) break
    await new Promise((wait) => setTimeout(wait, 50))
  }
  const login = await fetch(`${base}/operador/sesion`, {
    method: 'POST',
    redirect: 'manual',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: base, 'Sec-Fetch-Site': 'same-origin' },
    body: new URLSearchParams({ admin_key: ADMIN, operator_key: ANA }),
  })
  operator = (login.headers.getSetCookie().find((c) => c.startsWith('cecilai_operator=')) ?? '').split(';')[0]
  assert.ok(operator, 'the console session was opened')
})
after(() => {
  server.kill()
  api.closeAllConnections()
  api.close()
})

const customer = { Cookie: `cecilai_session=${TOKEN}` }
// The console's cookie is known only once `before` has logged in: the tables below are read when the tests are declared.
const asOperator = () => ({ Cookie: operator })
const get = (path: string, headers: Record<string, string> = {}) => fetch(`${base}${path}`, { headers, redirect: 'manual' })
const call = (name: string, init: { method?: 'GET' | 'POST'; data?: unknown; headers?: Record<string, string> }) => fetch(rpcRequest(base, name, init))
const PRIVATE = 'private, no-store'

describe('everything the BFF answers with a person\'s data forbids a cache', () => {
  const pages: [string, string, () => Record<string, string>, number][] = [
    ['the chat page', '/chat', () => customer, 200],
    ['the sign-in page', '/login', () => ({}), 200],
    ['a redirect to sign in', '/chat', () => ({}), 307],
    ['the queue', '/operador/cola', asOperator, 200],
    ['a ticket', '/operador/cola/TKT-0001-ABCD', asOperator, 200],
    ['a page that does not exist', '/no-such-page', () => ({}), 404],
  ]
  for (const [label, path, headers, status] of pages) {
    test(`${label}: ${path}`, async () => {
      const res = await get(path, headers())
      assert.equal(res.status, status, res.headers.get('location') ?? '')
      assert.equal(res.headers.get('cache-control'), PRIVATE)
      assert.equal(res.headers.get('pragma'), 'no-cache')
      await res.arrayBuffer()
    })
  }

  const reads: [string, string, unknown, () => Record<string, string>][] = [
    ['the conversation', 'getHistory', undefined, () => customer],
    ['the session', 'getSession', undefined, () => customer],
    ['the queue', 'loadQueue', false, asOperator],
    ['a ticket', 'loadTicket', { ticket_id: 'TKT-0001-ABCD' }, asOperator],
    ['a customer\'s context', 'loadCustomerContext', { ticket_id: 'TKT-0001-ABCD' }, asOperator],
    ['a read that fails validation', 'loadTicket', { ticket_id: '!' }, asOperator],
  ]
  for (const [label, name, data, headers] of reads) {
    test(`the server function that reads ${label} (GET ${name})`, async () => {
      const res = await call(name, { method: 'GET', data, headers: headers() })
      assert.equal(res.headers.get('cache-control'), PRIVATE)
      assert.equal(res.headers.get('pragma'), 'no-cache')
      await res.arrayBuffer()
    })
  }

  test('a server function that writes (the operator\'s decision) and a form post answer the same way', async () => {
    const decision = await call('actOnTicket', { data: { ticket_id: 'TKT-0001-ABCD', action: 'claim' }, headers: { Cookie: operator } })
    assert.equal(decision.headers.get('cache-control'), PRIVATE)
    const form = await fetch(`${base}/operador/salir`, { method: 'POST', redirect: 'manual', headers: { Origin: base, 'Sec-Fetch-Site': 'same-origin', Cookie: operator } })
    assert.equal(form.headers.get('cache-control'), PRIVATE)
  })

  test('a request the server refuses before the app (a bad target) is not cacheable either', async () => {
    const bad = await get('/%E0%A4%A')
    assert.equal(bad.status, 400)
    assert.equal(bad.headers.get('cache-control'), 'no-store')
  })
})

describe('what the build ships is still cacheable', () => {
  test('a hashed asset is public and immutable, and has no no-store', async () => {
    const asset = readdirSync(join(web, 'dist/client/assets')).find((f) => f.endsWith('.js')) as string
    const res = await get(`/assets/${asset}`)
    assert.equal(res.headers.get('cache-control'), 'public, max-age=31536000, immutable')
    assert.equal(res.headers.get('pragma'), null)
    await res.arrayBuffer()
  })

  test('a file at the root of the build is public for five minutes', async () => {
    const file = readdirSync(join(web, 'dist/client')).find((f) => f.endsWith('.png')) as string
    const res = await get(`/${file}`)
    assert.equal(res.headers.get('cache-control'), 'public, max-age=300')
    await res.arrayBuffer()
  })
})
