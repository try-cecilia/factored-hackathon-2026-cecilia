import assert from 'node:assert/strict'
import { test } from 'node:test'
import { loadHistory, parseHistory, type HistoryTransport } from './history-core.ts'
import type { ChatSession } from './chat-core.ts'
import { classifyReply } from '../chat/conversation.ts'

const turnsList = [
  { role: 'user', text: 'Me clonaron la tarjeta', at: 1_760_000_000.5 },
  {
    role: 'assistant', text: 'Voy a transferir tu caso.', at: 1_760_000_001, trace_id: 'abc12345', disposition: 'ESCALATE',
    category: 'theft', language: 'es', ticket_id: 'T-0123456789', degraded: true,
  },
]

const cases = [{ ticket_id: '55d09c14-2235-4c3c-8967-ccac61db9c50', category: 'theft', at: 1_760_000_001 }]

function setup(status: number, body: unknown) {
  const cleared: string[] = []
  const session: ChatSession = { token: 'tok-1', clear: () => cleared.push('cleared') }
  const transport: HistoryTransport = { get: async () => ({ status, json: async () => body }) }
  return { session, transport, cleared }
}

test('the turns come back in order, times in milliseconds, replies in the shape of a live reply', async () => {
  const { session, transport } = setup(200, { turns: turnsList, cases: cases })
  const result = await loadHistory(session, transport)
  assert.ok(result.ok)
  assert.deepEqual(result.turns[0], { role: 'user', text: 'Me clonaron la tarjeta', at: 1_760_000_000_500 })
  const second = result.turns[1]
  assert.ok(second.role === 'assistant')
  assert.equal(second.reply.response_text, 'Voy a transferir tu caso.')
  assert.equal(second.reply.ticket_id, 'T-0123456789')
  assert.equal(second.reply.degraded, true)
  assert.equal(second.reply.disposition, 'ESCALATE')
  assert.deepEqual(result.cases, [{ ticketId: '55d09c14-2235-4c3c-8967-ccac61db9c50', category: 'theft', at: 1_760_000_001_000 }])
})

test('an empty conversation is an empty list, not an error', async () => {
  const { session, transport } = setup(200, { turns: [], cases: [] })
  assert.deepEqual(await loadHistory(session, transport), { ok: true, turns: [], cases: [] })
})

test('a turn that does not fit the contract is left out and the rest still shows', () => {
  const kept = parseHistory({ turns: [turnsList[0], { role: 'assistant', text: 'x', at: 1, disposition: 'MAYBE', trace_id: 't' }, { role: 'robot', text: 'x', at: 1 }, 7, turnsList[1]], cases: [{ ticket_id: 'T-1', category: 'theft', at: 2 }, { ticket_id: 5 }, 'x'] })
  assert.equal(kept?.turns.length, 2)
  assert.deepEqual(kept?.cases, [{ ticketId: 'T-1', category: 'theft', at: 2000 }])
  assert.equal(parseHistory({ not: 'a list' }), null)
  assert.equal(parseHistory([]), null)
  assert.deepEqual(parseHistory({ turns: [] }), { turns: [], cases: [] })
})

test('a 401 clears the cookie and says the session is over; no cookie sends nothing', async () => {
  const { session, transport, cleared } = setup(401, {})
  assert.deepEqual(await loadHistory(session, transport), { ok: false, failure: 'session_expired' })
  assert.equal(cleared.length, 1)
  const none = setup(200, { turns: turnsList, cases: cases })
  assert.deepEqual(await loadHistory({ token: undefined, clear: () => {} }, none.transport), { ok: false, failure: 'session_expired' })
})

test('an API that is down or answers nonsense is "unavailable"', async () => {
  assert.deepEqual(await loadHistory(setup(503, {}).session, setup(503, {}).transport), { ok: false, failure: 'unavailable' })
  assert.deepEqual(await loadHistory(setup(200, 'nope').session, setup(200, 'nope').transport), { ok: false, failure: 'unavailable' })
  const throwing: HistoryTransport = { get: async () => { throw new Error('down') } }
  assert.deepEqual(await loadHistory({ token: 't', clear: () => {} }, throwing), { ok: false, failure: 'unavailable' })
})

test('a saved turn keeps the kind of its options, and one saved before it existed is still read as before', async () => {
  const movement = 'Tienes varios movimientos pendientes: 1) transferencia de 640.00 USD (Cuenta Corriente ···0015); 2) pago de 250.00 USD (Tarjeta Crédito ···0016). ¿Cuál quieres rastrear? Responde con su número.'
  const saved = (extra: object) => ({ role: 'assistant', text: movement, at: 1, trace_id: 'abc12345', disposition: 'CLARIFY', category: 'missing_or_invalid_argument', language: 'es', ...extra })
  const kept = parseHistory({ turns: [saved({ choice: 'movement' }), saved({}), saved({ choice: null })], cases: [] })
  assert.equal(kept?.turns.length, 3)
  const replies = kept!.turns.map((t) => (t.role === 'assistant' ? t.reply : null))
  assert.deepEqual(replies.map((r) => r?.choice), ['movement', undefined, undefined])
  // the screen reads the two without it by the sentence that introduces the options, so the number is what it sends
  for (const reply of replies) assert.equal(classifyReply(reply!).kind === 'clarify' && (classifyReply(reply!) as { options: { kind: string } }).options.kind, 'movement')
})
