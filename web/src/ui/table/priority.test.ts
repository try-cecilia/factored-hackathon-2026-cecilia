import assert from 'node:assert/strict'
import { test } from 'node:test'
import { comparePriority, priorities, priorityRank } from './priority.ts'

test('critical is the most urgent and low the least', () => {
  assert.deepEqual(priorities, ['critical', 'high', 'medium', 'low'])
  assert.deepEqual(priorities.map(priorityRank), [0, 1, 2, 3])
})

test('comparePriority puts urgent first and unknown values last', () => {
  assert.deepEqual(['low', 'critical', 'medium', 'nope', 'high'].sort(comparePriority), ['critical', 'high', 'medium', 'low', 'nope'])
})
