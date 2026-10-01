import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { QueueRow } from '../../server/queue-row.ts'
import { familyOf, isOverdue, overdueBy, TARGET_MINUTES, targetOf, targetShort } from './sla.ts'

const NOW = Date.UTC(2026, 8, 29, 12, 0, 0) // a fixed clock: nothing here reads the real one
const minutesAgo = (m: number) => (NOW - m * 60_000) / 1000

function row(over: Partial<QueueRow> & { status?: QueueRow['desk']['status'] } = {}): QueueRow {
  const { status = 'open', ...rest } = over
  return {
    ticket_id: 't1', created_at: minutesAgo(1), category: 'fraud', priority: 'High', queue: 'fraud_ops',
    customer_id: 'C-1', country: 'MX', language: 'es', request: 'r', desk: { status, operator: null, version: 0 }, ...rest,
  }
}

test('every category the console knows falls in a family, and an unknown one in the slowest', () => {
  assert.equal(familyOf('fraud'), 'security')
  assert.equal(familyOf('account_takeover'), 'security')
  assert.equal(familyOf('legal_or_regulator'), 'regulatory')
  assert.equal(familyOf('tool_failure'), 'service')
  assert.equal(familyOf('something_new'), 'service')
  assert.equal(familyOf(undefined), 'service')
})

test('fraud and security have a shorter objective than the rest', () => {
  assert.ok(TARGET_MINUTES.security < TARGET_MINUTES.regulatory)
  assert.ok(TARGET_MINUTES.regulatory < TARGET_MINUTES.service)
})

test('an open case is overdue only after its objective, and exactly at it is not yet', () => {
  const target = TARGET_MINUTES.security
  assert.equal(isOverdue(row({ created_at: minutesAgo(target - 1) }), NOW), false)
  assert.equal(isOverdue(row({ created_at: minutesAgo(target) }), NOW), false)
  assert.equal(isOverdue(row({ created_at: minutesAgo(target + 1) }), NOW), true)
})

test('the same wait is overdue for fraud and not for a service failure', () => {
  const created_at = minutesAgo(TARGET_MINUTES.security + 5)
  assert.equal(isOverdue(row({ category: 'fraud', created_at }), NOW), true)
  assert.equal(isOverdue(row({ category: 'tool_failure', created_at }), NOW), false)
})

test('a case someone took or decided is not overdue: the objective is the wait for a first person', () => {
  const created_at = minutesAgo(TARGET_MINUTES.service * 3)
  assert.equal(isOverdue(row({ status: 'claimed', created_at }), NOW), false)
  assert.equal(isOverdue(row({ status: 'approved', created_at }), NOW), false)
  assert.equal(isOverdue(row({ status: 'stale', created_at }), NOW), false)
})

test('a case without a creation time is never called overdue', () => {
  assert.equal(isOverdue(row({ created_at: 0 }), NOW), false)
})

test('how long past the objective, in whole minutes, and null when not overdue', () => {
  assert.equal(overdueBy(row({ created_at: minutesAgo(TARGET_MINUTES.security + 7) }), NOW), 7)
  assert.equal(overdueBy(row({ created_at: minutesAgo(1) }), NOW), null)
})

test('the objective is written as a compact span, like the age column', () => {
  assert.equal(targetShort(15), '15m')
  assert.equal(targetShort(120), '2h')
  assert.equal(targetShort(240), '4h')
  assert.equal(targetOf(row({ category: 'fraud' })), TARGET_MINUTES.security)
})
