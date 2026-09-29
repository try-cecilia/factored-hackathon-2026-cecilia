import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sendChat, type ChatSession, type ChatTransport } from './chat-core.ts'

const reply = {
  trace_id: 't1',
  disposition: 'AUTO_RESOLVE',
  response_text: 'Hola',
  language: 'es',
  category: 'resolved',
  ticket_id: null,
  latency_ms: 3,
}

function setup(status: number, body: unknown) {
  const cleared: string[] = []
  const session: ChatSession = { token: 'tok-1', clear: () => cleared.push('cleared') }
  const transport: ChatTransport = {
    post: async () => ({ status, json: async () => body }),
    failureOf: () => null,
  }
  return { session, transport, cleared }
}

test('a plain answer reaches the customer', async () => {
  const { session, transport } = setup(200, reply)
  const result = await sendChat(session, transport, 'hola')
  assert.ok(result.ok && result.reply.response_text === 'Hola')
})

test('a 401 from the API ends the session like REAUTH_REQUIRED does: cookie cleared, back to sign in', async () => {
  const { session, transport, cleared } = setup(401, { detail: 'invalid or expired session' })
  assert.deepEqual(await sendChat(session, transport, 'hola'), { ok: false, failure: 'session_expired' })
  assert.equal(cleared.length, 1)
})

test('REAUTH_REQUIRED clears the cookie and asks to sign in again', async () => {
  const { session, transport, cleared } = setup(200, { ...reply, disposition: 'REAUTH_REQUIRED' })
  assert.deepEqual(await sendChat(session, transport, 'hola'), { ok: false, failure: 'session_expired' })
  assert.equal(cleared.length, 1)
})

test('no cookie means the session is over, and nothing is sent', async () => {
  const { transport } = setup(200, reply)
  const cleared: string[] = []
  const result = await sendChat({ token: undefined, clear: () => cleared.push('x') }, transport, 'hola')
  assert.deepEqual(result, { ok: false, failure: 'session_expired' })
})

test('429, 5xx and a body that is not a chat answer are told apart', async () => {
  assert.deepEqual(await sendChat(...args(setup(429, {}))), { ok: false, failure: 'rate_limited' })
  assert.deepEqual(await sendChat(...args(setup(503, {}))), { ok: false, failure: 'unavailable' })
  assert.deepEqual(await sendChat(...args(setup(422, {}))), { ok: false, failure: 'unexpected' })
  assert.deepEqual(await sendChat(...args(setup(200, { hello: 'world' }))), { ok: false, failure: 'unexpected' })
})

function args(s: ReturnType<typeof setup>): [ChatSession, ChatTransport, string] {
  return [s.session, s.transport, 'hola']
}
