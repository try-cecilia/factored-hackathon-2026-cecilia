import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isMessageDisposition, resolveMessage, variantForDisposition } from './disposition.ts'

test('each disposition maps to its message variant', () => {
  assert.equal(variantForDisposition('AUTO_RESOLVE'), 'answer')
  assert.equal(variantForDisposition('CLARIFY'), 'clarify')
  assert.equal(variantForDisposition('ABSTAIN'), 'decline')
  assert.equal(variantForDisposition('ESCALATE'), 'handoff')
  assert.equal(variantForDisposition('REAUTH_REQUIRED'), 'signInAgain')
})

test('an unknown disposition never renders as an answer', () => {
  assert.equal(variantForDisposition('SOMETHING_NEW'), 'couldNotVerify')
  assert.equal(variantForDisposition(''), 'couldNotVerify')
  assert.equal(variantForDisposition('constructor'), 'couldNotVerify')
  assert.equal(isMessageDisposition('toString'), false)
  assert.equal(isMessageDisposition('CLARIFY'), true)
})

test('degraded mode adds the banner and keeps the variant of the disposition', () => {
  assert.deepEqual(resolveMessage({ disposition: 'AUTO_RESOLVE', degraded: true }), { variant: 'answer', limitedBanner: true })
  assert.deepEqual(resolveMessage({ disposition: 'ESCALATE' }), { variant: 'handoff', limitedBanner: false })
  assert.deepEqual(resolveMessage({ disposition: 'ABSTAIN', degraded: false }), { variant: 'decline', limitedBanner: false })
})
