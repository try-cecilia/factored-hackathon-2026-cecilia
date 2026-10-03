import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DEMO_ACTOR, SOMEONE_ELSE, parseDemoDeskAction, resolveResultsOf, withoutNames } from './demo-desk-core.ts'

test('resolving needs a predefined result; the message is optional, trimmed, on one line and cut at 500 characters', () => {
  assert.deepEqual(parseDemoDeskAction({ action: 'resolve', expected_version: 2, result_code: 'will_contact', message: '  Ya hablamos.\n\nTe avisamos. ' }), {
    action: 'resolve', expected_version: 2, reason: undefined, result_code: 'will_contact', message: 'Ya hablamos. Te avisamos.',
  })
  assert.equal(parseDemoDeskAction({ action: 'resolve', result_code: 'will_contact', message: 'a'.repeat(600) }).message, 'a'.repeat(500))
  for (const message of [undefined, '', '   \n ']) assert.equal(parseDemoDeskAction({ action: 'resolve', result_code: 'will_contact', message }).message, undefined)
  for (const result_code of [undefined, '', '  ', 42]) assert.throws(() => parseDemoDeskAction({ action: 'resolve', result_code, message: 'hola' }), /result_code is required/, String(result_code))
  for (const result_code of ['Will-Contact', 'a b', 'x'.repeat(65), '../admin']) assert.throws(() => parseDemoDeskAction({ action: 'resolve', result_code }), /result_code is not valid/, result_code)
})

test('only a resolution carries a result and a message, only a rejection a reason; no actor travels whatever the body says', () => {
  const claim = parseDemoDeskAction({ action: 'claim', expected_version: 0, result_code: 'will_contact', message: 'x', reason: 'y', operator: 'ana' })
  assert.deepEqual(claim, { action: 'claim', expected_version: 0, reason: undefined, result_code: undefined, message: undefined })
  assert.deepEqual(parseDemoDeskAction({ action: 'reject', reason: '  duplicado ' }).reason, 'duplicado')
  assert.equal(parseDemoDeskAction({ action: 'reject', reason: 'r'.repeat(400) }).reason, 'r'.repeat(300))
  assert.ok(!('operator' in claim))
  assert.throws(() => parseDemoDeskAction({ action: 'close' }), /action is not valid/)
  assert.throws(() => parseDemoDeskAction({ action: 'claim', expected_version: -1 }), /expected_version/)
  assert.throws(() => parseDemoDeskAction({ action: 'claim', expected_version: '1' }), /expected_version/)
})

test('the results of a case keep the API order and leave out anything that is not a code', () => {
  assert.deepEqual(resolveResultsOf(['charge_confirmed', 'will_contact', 7, 'Bad Code', 'will_contact', 'call_the_bank']), ['charge_confirmed', 'will_contact', 'call_the_bank'])
  assert.deepEqual(resolveResultsOf(undefined), [])
  assert.deepEqual(resolveResultsOf('will_contact'), [])
})

test('the visitor never reads the name of a person of the team: only the demo keeps its own', () => {
  const desk = { status: 'resolved', operator: 'ana', version: 3, history: [{ operator: 'demo', action: 'claim' }, { operator: 'ana', action: 'resolve' }] }
  const masked = withoutNames(desk)
  assert.equal(masked.operator, SOMEONE_ELSE)
  assert.deepEqual(masked.history.map((h) => h.operator), [DEMO_ACTOR, SOMEONE_ELSE])
  assert.ok(!JSON.stringify(masked).includes('ana'))
  assert.equal(withoutNames({ operator: null }).operator, null)
  assert.equal(withoutNames({ operator: 'demo' }).operator, 'demo')
})
