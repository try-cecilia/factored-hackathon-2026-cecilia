import assert from 'node:assert/strict'
import { test } from 'node:test'
import { comparePriority, priorities, priorityOf, priorityRank } from './priority.ts'

test('critical is the most urgent and low the least', () => {
  assert.deepEqual(priorities, ['critical', 'high', 'medium', 'low'])
  assert.deepEqual(priorities.map(priorityRank), [0, 1, 2, 3])
})

test('comparePriority puts urgent first and unknown values last', () => {
  assert.deepEqual(['low', 'critical', 'medium', 'nope', 'high'].sort(comparePriority), ['critical', 'high', 'medium', 'low', 'nope'])
})

test('the API priority is read in the kit terms; a missing or unknown one is `unknown`, never one of the four', () => {
  assert.equal(priorityOf('High'), 'high')
  assert.equal(priorityOf('critical'), 'critical')
  for (const missing of [undefined, null, '', 'Urgent', 'constructor']) assert.equal(priorityOf(missing), 'unknown', String(missing))
  assert.equal(priorityRank(priorityOf(undefined)), 4)
})
