import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isSelected, pruneSelection, selectAllState, toggleAll, toggleId } from './selection.ts'

test('toggleId adds a missing id and removes a present one without touching the input', () => {
  const selected = ['a', 'b']
  assert.deepEqual(toggleId(selected, 'c'), ['a', 'b', 'c'])
  assert.deepEqual(toggleId(selected, 'a'), ['b'])
  assert.deepEqual(selected, ['a', 'b'])
  assert.equal(isSelected(selected, 'b'), true)
  assert.equal(isSelected(selected, 'z'), false)
})

test('selectAllState is none, some (indeterminate) or all', () => {
  const visible = ['a', 'b', 'c']
  assert.equal(selectAllState(visible, []), 'none')
  assert.equal(selectAllState(visible, ['b']), 'some')
  assert.equal(selectAllState(visible, ['a', 'b', 'c']), 'all')
  assert.equal(selectAllState([], ['a']), 'none')
})

test('ids selected elsewhere do not count for the rows on screen', () => {
  assert.equal(selectAllState(['a', 'b'], ['x', 'y']), 'none')
  assert.equal(selectAllState(['a', 'b'], ['a', 'b', 'x']), 'all')
  assert.equal(selectAllState(['a', 'b'], ['a', 'x']), 'some')
})

test('toggleAll selects the missing rows when none or some are selected', () => {
  assert.deepEqual(toggleAll(['a', 'b', 'c'], []), ['a', 'b', 'c'])
  assert.deepEqual(toggleAll(['a', 'b', 'c'], ['b']), ['b', 'a', 'c'])
})

test('toggleAll clears the rows on screen when all are selected and keeps other pages', () => {
  assert.deepEqual(toggleAll(['a', 'b'], ['a', 'b']), [])
  assert.deepEqual(toggleAll(['a', 'b'], ['x', 'a', 'b']), ['x'])
  assert.deepEqual(toggleAll(['a', 'b'], ['x']), ['x', 'a', 'b'])
})

test('toggleAll with no rows changes nothing', () => {
  assert.deepEqual(toggleAll([], ['x']), ['x'])
})

test('pruneSelection drops ids that no longer exist', () => {
  assert.deepEqual(pruneSelection(['a', 'b', 'c'], ['b', 'c', 'd']), ['b', 'c'])
  assert.deepEqual(pruneSelection([], ['a']), [])
})
