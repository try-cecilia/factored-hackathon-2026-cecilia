import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseTraces } from './demo-core.ts'

const record = {
  trace_id: 'TR-15B5F466D9D65B60', customer_id: 'CLI-FIX0004', transaction_id: 'TXN-FIX0006', product_id: 'PRD-FIX0010',
  session_ref: 'a1b2c3', created_at: 1_760_000_000.5, status: 'open', sla_business_days: 2, queue: 'payments_ops',
}

test('a trace request keeps what the bank view shows and nothing of the customer, the product or the session', () => {
  assert.deepEqual(parseTraces([record]), [{
    trace_id: 'TR-15B5F466D9D65B60', transaction_id: 'TXN-FIX0006', queue: 'payments_ops', status: 'open', sla_business_days: 2, created_at: 1_760_000_000.5,
  }])
})

test('what does not fit is left out, and the rest stays; no list is no requests', () => {
  assert.deepEqual(parseTraces([null, 'x', { status: 'open' }, { trace_id: '' }, record]).map((t) => t.trace_id), ['TR-15B5F466D9D65B60'])
  assert.deepEqual(parseTraces({ error: 'x' }), [])
  assert.deepEqual(parseTraces(undefined), [])
})

test('a field of the wrong type is an empty one, not a thrown error', () => {
  assert.deepEqual(parseTraces([{ trace_id: 'TR-1', status: 5, queue: null, sla_business_days: 'dos', transaction_id: 7, created_at: NaN }]), [
    { trace_id: 'TR-1', transaction_id: '', queue: '', status: '', sla_business_days: null, created_at: 0 },
  ])
})

test('a deadline the API does not give is none, never 0; the zero of a rule stays zero', () => {
  const { sla_business_days: _, ...withoutDeadline } = record
  assert.equal(parseTraces([withoutDeadline])[0].sla_business_days, null)
  assert.equal(parseTraces([{ ...record, sla_business_days: null }])[0].sla_business_days, null)
  assert.equal(parseTraces([{ ...record, sla_business_days: 1.5 }])[0].sla_business_days, null)
  assert.equal(parseTraces([{ ...record, sla_business_days: -2 }])[0].sla_business_days, null)
  assert.equal(parseTraces([{ ...record, sla_business_days: 0 }])[0].sla_business_days, 0)
})
