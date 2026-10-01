import assert from 'node:assert/strict'
import { test } from 'node:test'
import { classifyReply } from '../chat/conversation.ts'
import { KEY_PATTERN, parseReply, parseSend, sendChat, type ChatSession, type ChatTransport } from './chat-core.ts'

const KEY = '0b0c7b1e-6f43-4d59-8f5e-3f0f6a1f7c11'

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
  const result = await sendChat(session, transport, 'hola', KEY)
  assert.ok(result.ok && result.reply.response_text === 'Hola')
})

test('a 401 from the API ends the session like REAUTH_REQUIRED does: cookie cleared, back to sign in', async () => {
  const { session, transport, cleared } = setup(401, { detail: 'invalid or expired session' })
  assert.deepEqual(await sendChat(session, transport, 'hola', KEY), { ok: false, failure: 'session_expired' })
  assert.equal(cleared.length, 1)
})

test('REAUTH_REQUIRED clears the cookie and asks to sign in again', async () => {
  const { session, transport, cleared } = setup(200, { ...reply, disposition: 'REAUTH_REQUIRED' })
  assert.deepEqual(await sendChat(session, transport, 'hola', KEY), { ok: false, failure: 'session_expired' })
  assert.equal(cleared.length, 1)
})

test('no cookie means the session is over, and nothing is sent', async () => {
  const { transport } = setup(200, reply)
  const cleared: string[] = []
  const result = await sendChat({ token: undefined, clear: () => cleared.push('x') }, transport, 'hola', KEY)
  assert.deepEqual(result, { ok: false, failure: 'session_expired' })
})

test('429, 5xx and a body that is not a chat answer are told apart', async () => {
  assert.deepEqual(await sendChat(...args(setup(429, {}))), { ok: false, failure: 'rate_limited' })
  assert.deepEqual(await sendChat(...args(setup(503, {}))), { ok: false, failure: 'unavailable' })
  assert.deepEqual(await sendChat(...args(setup(422, {}))), { ok: false, failure: 'unexpected' })
  assert.deepEqual(await sendChat(...args(setup(409, {}))), { ok: false, failure: 'already_processed' })
  assert.deepEqual(await sendChat(...args(setup(200, { hello: 'world' }))), { ok: false, failure: 'unexpected' })
})

function args(s: ReturnType<typeof setup>): [ChatSession, ChatTransport, string, string] {
  return [s.session, s.transport, 'hola', KEY]
}

test('the key goes to the API with the message', async () => {
  const seen: string[] = []
  const transport: ChatTransport = {
    post: async (_token, message, key) => {
      seen.push(`${message}|${key}`)
      return { status: 200, json: async () => reply }
    },
    failureOf: () => null,
  }
  await sendChat({ token: 'tok-1', clear: () => {} }, transport, 'hola', KEY)
  assert.deepEqual(seen, [`hola|${KEY}`])
})

test('a retry after a connection that dropped sends the same key, and gets the reply the API kept', async () => {
  const keys: string[] = []
  let calls = 0
  const transport: ChatTransport = {
    post: async (_token, _message, key) => {
      keys.push(key)
      if (++calls === 1) throw new Error('socket hang up') // the API may have processed it
      return { status: 200, json: async () => reply }
    },
    failureOf: () => ({ ok: false, failure: 'unavailable' }),
  }
  const session: ChatSession = { token: 'tok-1', clear: () => {} }
  assert.deepEqual(await sendChat(session, transport, 'hola', KEY), { ok: false, failure: 'unavailable' })
  const again = await sendChat(session, transport, 'hola', KEY)
  assert.ok(again.ok)
  assert.deepEqual(keys, [KEY, KEY])
})

test('a send without a valid key is refused before it reaches the API', () => {
  assert.deepEqual(parseSend({ message: '  hola ', key: KEY }), { message: 'hola', key: KEY })
  assert.throws(() => parseSend({ message: 'hola' }))
  assert.throws(() => parseSend({ message: 'hola', key: 'short' }))
  assert.throws(() => parseSend({ message: 'hola', key: 'has spaces in it!' }))
  assert.throws(() => parseSend({ message: '   ', key: KEY }))
  assert.ok(KEY_PATTERN.test(KEY))
})

test('the kind of the options of a clarification comes through, and only a known one', () => {
  assert.equal(parseReply({ ...reply, disposition: 'CLARIFY', choice: 'product' })?.choice, 'product')
  assert.equal(parseReply({ ...reply, disposition: 'CLARIFY', choice: 'movement' })?.choice, 'movement')
  assert.equal(parseReply({ ...reply, choice: 'other' })?.choice, undefined)
  assert.equal(parseReply({ ...reply, choice: null })?.choice, undefined)
})

test('a reply without the kind of its options (an older API, a stored replay) has none, and the screen reads the text as before', async () => {
  const text = 'Você tem várias movimentações pendentes: 1) a (X ···1); 2) b (Y ···2). Qual quer rastrear? Responda com o número.'
  const body = { ...reply, disposition: 'CLARIFY', language: 'pt', response_text: text }
  for (const old of [body, { ...body, choice: null }]) {
    const parsed = parseReply(old)
    assert.equal(parsed?.choice, undefined)
    const kind = classifyReply(parsed!)
    assert.equal(kind.kind === 'clarify' && kind.options?.kind, 'movement')
  }
})
