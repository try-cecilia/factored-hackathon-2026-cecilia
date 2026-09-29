import assert from 'node:assert/strict'
import { test } from 'node:test'
import { loadHistory, parseHistory, type HistoryTransport } from './history-core.ts'
import type { ChatSession } from './chat-core.ts'

const turns = [
  { role: 'user', text: 'Me clonaron la tarjeta', at: 1_760_000_000.5 },
  {
    role: 'assistant', text: 'Voy a transferir tu caso.', at: 1_760_000_001, trace_id: 'abc12345', disposition: 'ESCALATE',
    category: 'theft', language: 'es', ticket_id: 'T-0123456789', degraded: true,
  },
]

function setup(status: number, body: unknown) {
  const cleared: string[] = []
  const session: ChatSession = { token: 'tok-1', clear: () => cleared.push('cleared') }
  const transport: HistoryTransport = { get: async () => ({ status, json: async () => body }) }
  return { session, transport, cleared }
}

test('the turns come back in order, times in milliseconds, replies in the shape of a live reply', async () => {
  const { session, transport } = setup(200, turns)
  const result = await loadHistory(session, transport)
  assert.ok(result.ok)
  assert.deepEqual(result.turns[0], { role: 'user', text: 'Me clonaron la tarjeta', at: 1_760_000_000_500 })
  const second = result.turns[1]
  assert.ok(second.role === 'assistant')
  assert.equal(second.reply.response_text, 'Voy a transferir tu caso.')
  assert.equal(second.reply.ticket_id, 'T-0123456789')
  assert.equal(second.reply.degraded, true)
  assert.equal(second.reply.disposition, 'ESCALATE')
})

test('an empty conversation is an empty list, not an error', async () => {
  const { session, transport } = setup(200, [])
  assert.deepEqual(await loadHistory(session, transport), { ok: true, turns: [] })
})

test('a turn that does not fit the contract is left out and the rest still shows', () => {
  const kept = parseHistory([turns[0], { role: 'assistant', text: 'x', at: 1, disposition: 'MAYBE', trace_id: 't' }, { role: 'robot', text: 'x', at: 1 }, 7, turns[1]])
  assert.equal(kept?.length, 2)
  assert.equal(parseHistory({ not: 'a list' }), null)
})

test('a 401 clears the cookie and says the session is over; no cookie sends nothing', async () => {
  const { session, transport, cleared } = setup(401, {})
  assert.deepEqual(await loadHistory(session, transport), { ok: false, failure: 'session_expired' })
  assert.equal(cleared.length, 1)
  const none = setup(200, turns)
  assert.deepEqual(await loadHistory({ token: undefined, clear: () => {} }, none.transport), { ok: false, failure: 'session_expired' })
})

test('an API that is down or answers nonsense is "unavailable"', async () => {
  assert.deepEqual(await loadHistory(setup(503, {}).session, setup(503, {}).transport), { ok: false, failure: 'unavailable' })
  assert.deepEqual(await loadHistory(setup(200, 'nope').session, setup(200, 'nope').transport), { ok: false, failure: 'unavailable' })
  const throwing: HistoryTransport = { get: async () => { throw new Error('down') } }
  assert.deepEqual(await loadHistory({ token: 't', clear: () => {} }, throwing), { ok: false, failure: 'unavailable' })
})
