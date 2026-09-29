import assert from 'node:assert/strict'
import { test } from 'node:test'
import { initials } from './initials.ts'

test('two words give the first and last initial', () => {
  assert.equal(initials('Camila Ortega'), 'CO')
  assert.equal(initials('Juan Carlos de la Vega'), 'JV')
})

test('operator keys split on dots, underscores and dashes', () => {
  assert.equal(initials('ana.ruiz'), 'AR')
  assert.equal(initials('luis_mora-diaz'), 'LD')
})

test('one word gives its first two letters, and empty gives nothing', () => {
  assert.equal(initials('camila'), 'CA')
  assert.equal(initials('x'), 'X')
  assert.equal(initials('  '), '')
})
