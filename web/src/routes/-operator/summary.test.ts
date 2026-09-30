import assert from 'node:assert/strict'
import { test } from 'node:test'
import { es } from '../../i18n/es.ts'
import { translator } from '../../i18n/translate.ts'
import type { DeskState, Ticket } from '../../server/operator.functions.ts'
import { ticketSummary } from './summary.ts'

const ticket = (over: Partial<Ticket> = {}, desk: Partial<DeskState> = {}): Ticket => ({
  ticket_id: 'a91f3c00-5c2e', trace_id: null, created_at: 1, category: 'fraud', priority: 'High', queue: 'fraud_ops', customer_id: 'C-1',
  session_ref: 's-1', segment: null, country: 'México', language: 'es', request: 'No reconozco un cargo.', prior_requests: [],
  reason: 'The customer does not recognize a charge', policy_rule: 'fraud_review', verified_facts: [], evidence: [], actions_taken: [],
  open_questions: [], suggested_next_step: 'Call the customer.', pending_action: null,
  desk: { ticket_id: 'a91f3c00-5c2e', status: 'claimed', operator: 'ana.ruiz', trace_id: null, version: 1, history: [], ...desk },
  ...over,
})

const said = 'Era una suscripción; ya no se cobra.'
const resolve = { action: 'resolve', status: 'resolved', operator: 'ana.ruiz', ts: 2, detail: { message: said } }

test('the summary of a resolved case says so and carries the message the customer got', () => {
  const text = ticketSummary(ticket({}, { status: 'resolved', version: 2, message: said, history: [resolve] }), translator(es))
  assert.match(text, /^Estado: Resuelto \(ana\.ruiz\)$/m)
  assert.match(text, /^Mensaje para el cliente: Era una suscripción; ya no se cobra\.$/m)
  // An API that does not send the field still has the message in the history.
  assert.match(ticketSummary(ticket({}, { status: 'resolved', version: 2, history: [resolve] }), translator(es)), /^Mensaje para el cliente: Era una/m)
  assert.doesNotMatch(ticketSummary(ticket(), translator(es)), /Mensaje para el cliente/)
})
