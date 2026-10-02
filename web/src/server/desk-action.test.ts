import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseDeskAction } from './desk-action.ts'

test('resolving needs a message for the customer: trimmed, on one line and cut at 500 characters', () => {
  assert.deepEqual(parseDeskAction({ action: 'resolve', expected_version: 2, message: '  Revisamos el cargo.\n\nNo hace falta hacer nada más. ' }), {
    action: 'resolve', expected_version: 2, reason: undefined, message: 'Revisamos el cargo. No hace falta hacer nada más.',
  })
  assert.equal(parseDeskAction({ action: 'resolve', message: 'a'.repeat(600) }).message, 'a'.repeat(500))
  for (const message of [undefined, '', '  \n\t ', 42]) assert.throws(() => parseDeskAction({ action: 'resolve', message }), /message is required/, String(message))
})

test('the other actions are as before: a rejection keeps its reason and nothing asks for a message', () => {
  assert.deepEqual(parseDeskAction({ action: 'reject', expected_version: 1, reason: '  duplicado ' }), { action: 'reject', expected_version: 1, reason: 'duplicado', message: undefined })
  assert.deepEqual(parseDeskAction({ action: 'claim' }), { action: 'claim', expected_version: undefined, reason: undefined, message: undefined })
  assert.throws(() => parseDeskAction({ action: 'close' }), /action is not valid/)
  assert.throws(() => parseDeskAction({ action: 'approve', expected_version: '3' }), /expected_version/)
  assert.throws(() => parseDeskAction({ action: 'approve', expected_version: -10 }), /expected_version/)
  assert.deepEqual(parseDeskAction({ action: 'claim', expected_version: 0 }).expected_version, 0)
})
