import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ariaSort, compareValues, directionOf, nextSort, sortRows, type SortState } from './sort.ts'

test('the header click cycles none → asc → desc → none', () => {
  let sort: SortState = null
  sort = nextSort(sort, 'age')
  assert.deepEqual(sort, { key: 'age', direction: 'asc' })
  sort = nextSort(sort, 'age')
  assert.deepEqual(sort, { key: 'age', direction: 'desc' })
  sort = nextSort(sort, 'age')
  assert.equal(sort, null)
})

test('clicking another column starts at ascending, whatever the current direction', () => {
  assert.deepEqual(nextSort({ key: 'age', direction: 'desc' }, 'queue'), { key: 'queue', direction: 'asc' })
  assert.deepEqual(nextSort({ key: 'age', direction: 'asc' }, 'queue'), { key: 'queue', direction: 'asc' })
})

test('aria-sort is only ascending or descending on the sorted column', () => {
  const sort: SortState = { key: 'age', direction: 'desc' }
  assert.equal(ariaSort(sort, 'age'), 'descending')
  assert.equal(ariaSort(sort, 'queue'), 'none')
  assert.equal(ariaSort({ key: 'age', direction: 'asc' }, 'age'), 'ascending')
  assert.equal(ariaSort(null, 'age'), 'none')
  assert.equal(directionOf(sort, 'age'), 'desc')
  assert.equal(directionOf(sort, 'queue'), null)
})

test('compareValues orders numbers, dates and text with numeric collation', () => {
  assert.ok(compareValues(2, 10) < 0)
  assert.ok(compareValues('ticket 2', 'ticket 10') < 0)
  assert.ok(compareValues('álamo', 'Alamo') === 0)
  assert.ok(compareValues(new Date('2026-01-02'), new Date('2026-01-01')) > 0)
  assert.equal(compareValues(3, 3), 0)
})

test('empty values go after the rest', () => {
  assert.ok(compareValues(null, 1) > 0)
  assert.ok(compareValues(1, undefined) < 0)
  assert.ok(compareValues('', 'a') > 0)
  assert.equal(compareValues(null, undefined), 0)
})

test('sortRows orders by key, keeps ties in their original order and never mutates the input', () => {
  const rows = [
    { id: 'a', age: 30 },
    { id: 'b', age: 5 },
    { id: 'c', age: 30 },
    { id: 'd', age: 12 },
  ]
  const snapshot = structuredClone(rows)
  const value = (row: (typeof rows)[number], key: string) => (row as Record<string, unknown>)[key] as number
  assert.deepEqual(sortRows(rows, { key: 'age', direction: 'asc' }, value).map((r) => r.id), ['b', 'd', 'a', 'c'])
  assert.deepEqual(sortRows(rows, { key: 'age', direction: 'desc' }, value).map((r) => r.id), ['a', 'c', 'd', 'b'])
  assert.deepEqual(rows, snapshot)
})

test('sortRows without a sort returns a copy in the given order', () => {
  const rows = [{ id: 2 }, { id: 1 }]
  const result = sortRows(rows, null, (row) => row.id)
  assert.deepEqual(result, rows)
  assert.notEqual(result, rows)
})

test('sortRows keeps empty values last in both directions', () => {
  const rows = [{ id: 'a', v: null }, { id: 'b', v: 2 }, { id: 'c', v: 1 }] as { id: string; v: number | null }[]
  const value = (row: { v: number | null }) => row.v
  assert.deepEqual(sortRows(rows, { key: 'v', direction: 'asc' }, value).map((r) => r.id), ['c', 'b', 'a'])
  assert.deepEqual(sortRows(rows, { key: 'v', direction: 'desc' }, value).map((r) => r.id), ['b', 'c', 'a'])
})
