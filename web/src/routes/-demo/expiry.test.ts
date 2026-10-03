import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DEMO_WARN_SECONDS, demoClock, minutesSeconds } from './expiry.ts'

test('the bar warns in the last three minutes and says when it is over', () => {
  assert.deepEqual(demoClock(900), { state: 'running' })
  assert.deepEqual(demoClock(DEMO_WARN_SECONDS + 1), { state: 'running' })
  assert.deepEqual(demoClock(DEMO_WARN_SECONDS), { state: 'warning', seconds: 180 })
  assert.deepEqual(demoClock(0.2), { state: 'warning', seconds: 1 })
  assert.deepEqual(demoClock(0), { state: 'over' })
  assert.deepEqual(demoClock(-5), { state: 'over' })
  assert.equal(minutesSeconds(179), '2:59')
  assert.equal(minutesSeconds(60), '1:00')
  assert.equal(minutesSeconds(5), '0:05')
})
