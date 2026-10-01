import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { QueueRow } from '../../server/queue-row.ts'
import { addSeen, browserStore, readSeen, SEEN_KEY, settle, unseenIds, withCount, writeSeen } from './seen.ts'

const row = (id: string, status: QueueRow['desk']['status'] = 'open'): QueueRow => ({
  ticket_id: id, created_at: 1, category: 'fraud', priority: 'High', queue: 'fraud_ops', customer_id: 'C-1', country: 'MX', language: 'es', request: 'r',
  desk: { status, operator: null, version: 0 },
})

const memory = (start: Record<string, string> = {}) => {
  const data = { ...start }
  return { data, getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => void (data[k] = v) }
}

test('the first look at the queue marks nothing as new: everything in it is the baseline', () => {
  const rows = [row('a'), row('b'), row('c', 'approved')]
  const seen = settle(null, rows)
  assert.deepEqual(unseenIds(rows, new Set(seen)), [])
})

test('a case that arrives after the baseline is new until it is marked', () => {
  const seen = settle(null, [row('a'), row('b')])
  const later = [row('a'), row('b'), row('c'), row('d')]
  assert.deepEqual(unseenIds(later, new Set(settle(seen, later))), ['c', 'd'])
  // Another refresh with the same rows keeps them new: refreshing is not looking.
  assert.deepEqual(unseenIds(later, new Set(settle(settle(seen, later), later))), ['c', 'd'])
})

test('marking cases as seen removes exactly those', () => {
  const seen = settle(null, [row('a')])
  const later = [row('a'), row('c'), row('d')]
  const after = addSeen(settle(seen, later), ['c'])
  assert.deepEqual(unseenIds(later, new Set(after)), ['d'])
})

test('only pending work counts: a new case someone already decided is not news', () => {
  const seen = settle(null, [row('a')])
  const later = [row('a'), row('b', 'approved'), row('c', 'stale'), row('d', 'claimed'), row('e')]
  assert.deepEqual(unseenIds(later, new Set(settle(seen, later))), ['d', 'e'])
})

test('what left the list is forgotten, so the remembered set stays as small as the queue', () => {
  const seen = settle(null, [row('a'), row('b'), row('c')])
  assert.deepEqual(settle(seen, [row('b')]), ['b'])
})

test('the seen set is kept in the browser session, and a store that is missing or broken means never looked', () => {
  const store = memory()
  assert.equal(readSeen(store), null)
  writeSeen(store, ['a', 'b'])
  assert.deepEqual(readSeen(store), ['a', 'b'])
  assert.deepEqual(readSeen(memory({ [SEEN_KEY]: 'not json' })), null)
  assert.deepEqual(readSeen(memory({ [SEEN_KEY]: '{"a":1}' })), null)
  assert.deepEqual(readSeen(memory({ [SEEN_KEY]: '["a",3,null,"b"]' })), ['a', 'b'])
  const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } }
  assert.equal(readSeen(broken), null)
  assert.doesNotThrow(() => writeSeen(broken, ['a']))
  assert.equal(readSeen(undefined), null)
  assert.doesNotThrow(() => writeSeen(undefined, ['a']))
})

test('the tab title carries the count in front, once, and loses it at zero', () => {
  assert.equal(withCount('Cola · Cecilai', 3), '(3) Cola · Cecilai')
  assert.equal(withCount('(3) Cola · Cecilai', 5), '(5) Cola · Cecilai')
  assert.equal(withCount('(3) Cola · Cecilai', 0), 'Cola · Cecilai')
  assert.equal(withCount('Cola · Cecilai', 0), 'Cola · Cecilai')
  assert.equal(withCount('Caso (2) · Cecilai', 1), '(1) Caso (2) · Cecilai')
})

test('outside a browser there is no store, and asking for one does not throw', () => {
  assert.equal(browserStore(), undefined)
})
