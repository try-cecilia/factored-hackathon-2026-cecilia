import assert from 'node:assert/strict'
import { test } from 'node:test'
import { toCustomerContext } from './customer-context.ts'

const api = {
  warehouse: { available: true, as_of: '2026-06-01' },
  products: [{ product_id: 'PRD-1', type: 'Cuenta Ahorro', currency: 'USD', status: 'Active', last4: '0001' }],
  movements: [{ transaction_id: 'TXN-1', date: '2026-05-30T10:00:00', product_id: 'PRD-1', type: 'Transfer', amount: 40, currency: 'USD', merchant: null, status: 'Pending', pending: true }],
  cases: [{ ticket_id: 'T-1', category: 'fraud', queue: 'fraud_ops', priority: 'High', created_at: 1700000000, status: 'open' }],
  traces: [{ trace_id: 'TR-1', transaction_id: 'TXN-1', status: 'open', created_at: 1700000000 }],
}

test('what the API sends for the case passes through as it came', () => {
  assert.deepEqual(toCustomerContext(api), api)
})

test('only the fields the console shows leave the BFF, whatever else the API adds', () => {
  const noisy = {
    ...api,
    customer_id: 'CLI-1',
    products: [{ ...api.products[0], product_number: '4000000001', document: 'DNI9' }],
    movements: [{ ...api.movements[0], fraud_score: 99, latitude: 1.5 }],
  }
  const shaped = toCustomerContext(noisy)
  assert.deepEqual(shaped, api)
  assert.ok(!JSON.stringify(shaped).includes('4000000001'))
})

test('an account number can never travel: a product mark longer than four characters is dropped', () => {
  const shaped = toCustomerContext({ ...api, products: [{ ...api.products[0], last4: '4000000001' }, { ...api.products[0], product_id: 'PRD-2', last4: '1234' }] })
  assert.deepEqual(shaped?.products.map((p) => p.last4), [null, '1234'])
})

test('a warehouse that is down keeps the rest', () => {
  const down = { ...api, warehouse: { available: false, as_of: null }, products: [], movements: [] }
  assert.deepEqual(toCustomerContext(down), down)
})

test('a body that is not the contract is not a context, and a bad row is left out of its list', () => {
  assert.equal(toCustomerContext(null), null)
  assert.equal(toCustomerContext([]), null)
  assert.equal(toCustomerContext({ products: [] }), null) // no word on the warehouse
  const partial = toCustomerContext({ ...api, cases: [{ ticket_id: 7 }, api.cases[0], null], traces: 'x' })
  assert.deepEqual(partial?.cases, [api.cases[0]])
  assert.deepEqual(partial?.traces, [])
})
