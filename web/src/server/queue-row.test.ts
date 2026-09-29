import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Ticket } from './operator.functions.ts'
import { toQueueRow } from './queue-row.ts'

const ticket: Ticket = {
  ticket_id: '55d09c14-2235-4c3c-8967-ccac61db9c50', trace_id: 'abc12345', created_at: 1_760_000_001, category: 'theft', priority: 'Critical',
  queue: 'fraud_ops', customer_id: 'CLI-FIX0001', session_ref: 'ref-1', segment: 'Premium', country: 'México', language: 'es',
  request: 'Me clonaron la tarjeta', prior_requests: ['hola'], reason: 'fraude', policy_rule: 'card_theft',
  verified_facts: [{ card: '**** 4242', blocked: false }],
  evidence: [{ type: 'transaction', id: 'TX-1', flagged: true, detail: { amount: 120, merchant: 'X' } }],
  actions_taken: [{ tool: 'lookup_card' }], open_questions: ['¿Reconoce el cargo?'], suggested_next_step: 'Bloquear la tarjeta',
  pending_action: { tool: 'open_trace', transaction_id: 'TX-1', product_id: 'P-1' },
  desk: { ticket_id: '55d09c14-2235-4c3c-8967-ccac61db9c50', status: 'claimed', operator: 'ana.ruiz', trace_id: 'abc12345', version: 3, history: [{ action: 'claim', status: 'claimed', operator: 'ana.ruiz', ts: 1, detail: {} }] },
}

test('a queue row carries what the list, its filters and the sidebar use, and nothing of the case itself', () => {
  const row = toQueueRow(ticket)
  assert.deepEqual(row, {
    ticket_id: ticket.ticket_id, created_at: ticket.created_at, category: 'theft', priority: 'Critical', queue: 'fraud_ops',
    customer_id: 'CLI-FIX0001', country: 'México', language: 'es', request: 'Me clonaron la tarjeta',
    desk: { status: 'claimed', operator: 'ana.ruiz', version: 3 },
  })
  const wire = JSON.stringify(row)
  for (const kept of ['evidence', 'verified_facts', 'actions_taken', 'history', 'pending_action', 'prior_requests', 'session_ref', 'TX-1', '4242']) {
    assert.ok(!wire.includes(kept), kept)
  }
})
