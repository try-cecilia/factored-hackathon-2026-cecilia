import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clampPercent, connectorDone, spinnerArc, spinnerPixels, spinnerStroke, stepStatuses } from './progressMath.ts'

test('clampPercent keeps the value inside 0..100', () => {
  assert.equal(clampPercent(60), 60)
  assert.equal(clampPercent(-5), 0)
  assert.equal(clampPercent(140), 100)
  assert.equal(clampPercent(33.6), 34)
})

test('clampPercent honors a custom max and survives bad input', () => {
  assert.equal(clampPercent(3, 12), 25)
  assert.equal(clampPercent(Number.NaN), 0)
  assert.equal(clampPercent(5, 0), 0)
  assert.equal(clampPercent(Number.POSITIVE_INFINITY), 0)
})

test('spinner sizes and stroke follow Paper', () => {
  assert.deepEqual((['xs', 'sm', 'md', 'lg'] as const).map(spinnerPixels), [12, 16, 20, 28])
  assert.equal(spinnerPixels(14), 14)
  assert.equal(spinnerStroke(10), 3.5)
  assert.equal(spinnerStroke(14), 3)
  assert.equal(spinnerStroke(20), 3)
  assert.equal(spinnerStroke(28), 2.6)
})

test('the indeterminate spinner draws 30% and a determinate one draws its value', () => {
  assert.equal(spinnerArc(undefined), 0.3)
  assert.equal(spinnerArc(25), 0.25)
  assert.equal(spinnerArc(60), 0.6)
  assert.equal(spinnerArc(250), 1)
})

test('stepStatuses marks what came before as done and what follows as pending', () => {
  assert.deepEqual(stepStatuses(3, 1), ['done', 'active', 'pending'])
  assert.deepEqual(stepStatuses(3, 0), ['active', 'pending', 'pending'])
  assert.deepEqual(stepStatuses(3, 3), ['done', 'done', 'done'])
  assert.deepEqual(stepStatuses(0, 0), [])
})

test('a connector fills once the step before it is done', () => {
  const statuses = stepStatuses(3, 1)
  assert.equal(connectorDone(statuses, 0), true)
  assert.equal(connectorDone(statuses, 1), false)
})
