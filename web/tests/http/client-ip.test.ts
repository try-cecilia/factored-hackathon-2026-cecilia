// The browser's address reaches the API as X-Client-IP, vouched for by the secret the web and the API share
// (BFF_CLIENT_IP_SECRET): behind Render's edge every call from the web arrives from the web's own address, and the API
// believes a forwarded address only with that secret (api/main.py, client_ip).
import assert from 'node:assert/strict'
import type { IncomingHttpHeaders } from 'node:http'
import { after, before, beforeEach, describe, test } from 'node:test'
import { startCustomerApp, TOKEN } from './customer-harness.ts'

const SECRET = 'bff-secret-0123456789-abcdefgh'
const seen: IncomingHttpHeaders[] = []
let app: Awaited<ReturnType<typeof startCustomerApp>>

before(async () => {
  app = await startCustomerApp((req, reply) => {
    if (req.url !== '/chat/history') return false
    seen.push(req.headers)
    reply(200, { turns: [], cases: [] })
  })
  process.env.TRUSTED_CLIENT_IP_HEADER = 'CF-Connecting-IP'
})
after(() => {
  delete process.env.TRUSTED_CLIENT_IP_HEADER
  delete process.env.BFF_CLIENT_IP_SECRET
  return app.close()
})
beforeEach(() => void (seen.length = 0))

const asBrowser = (ip: string, extra: Record<string, string> = {}) => ({ Cookie: `cecilai_session=${TOKEN}`, 'CF-Connecting-IP': ip, ...extra })

describe('the browser address the web forwards to the API', () => {
  test('two browsers behind one web service reach the API with their own address and the shared secret', async () => {
    process.env.BFF_CLIENT_IP_SECRET = SECRET
    assert.equal((await app.get('/chat', asBrowser('203.0.113.7'))).status, 200)
    assert.equal((await app.get('/chat', asBrowser('198.51.100.9'))).status, 200)
    assert.deepEqual(seen.map((h) => h['x-client-ip']), ['203.0.113.7', '198.51.100.9'])
    assert.deepEqual(seen.map((h) => h['x-bff-secret']), [SECRET, SECRET])
  })

  test('what the browser itself sends as X-Client-IP or X-BFF-Secret is never passed on', async () => {
    process.env.BFF_CLIENT_IP_SECRET = SECRET
    await app.get('/chat', asBrowser('203.0.113.7', { 'X-Client-IP': '6.6.6.6', 'X-BFF-Secret': 'forged-by-the-browser' }))
    assert.equal(seen[0]['x-client-ip'], '203.0.113.7')
    assert.equal(seen[0]['x-bff-secret'], SECRET)
  })

  test('without the secret configured the web sends none, and the address as before', async () => {
    delete process.env.BFF_CLIENT_IP_SECRET
    await app.get('/chat', asBrowser('203.0.113.7', { 'X-BFF-Secret': 'forged-by-the-browser' }))
    assert.equal(seen[0]['x-client-ip'], '203.0.113.7')
    assert.equal(seen[0]['x-bff-secret'], undefined)
  })
})
