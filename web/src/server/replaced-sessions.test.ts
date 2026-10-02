import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ReplacedSessions } from './replaced-sessions.ts'

// The customer's explicit sign-out waits on the API before it answers; a login from the same browser may finish meanwhile and set a new
// cookie. The login says which token it replaced, and the sign-out asks before it sends a deletion that would take the new cookie.
test('a token the browser has replaced is known as replaced, for a while', () => {
  let now = 1_000
  const replaced = new ReplacedSessions(() => now, 60_000)
  replaced.note('tok-old')
  assert.equal(replaced.has('tok-old'), true)
  assert.equal(replaced.has('tok-other'), false)
  now += 59_000
  assert.equal(replaced.has('tok-old'), true)
  now += 2_000
  assert.equal(replaced.has('tok-old'), false)
})

test('a login without a cookie replaces nothing', () => {
  const replaced = new ReplacedSessions(() => 0, 60_000)
  replaced.note(undefined)
  assert.equal(replaced.has(undefined), false)
})

test('it holds a bounded number of tokens, the oldest going first, and never the token itself', () => {
  const replaced = new ReplacedSessions(() => 0, 60_000, 3)
  for (const token of ['a', 'b', 'c', 'd']) replaced.note(token)
  assert.equal(replaced.has('a'), false)
  for (const token of ['b', 'c', 'd']) assert.equal(replaced.has(token), true)
  assert.ok(!JSON.stringify([...replaced.entries()]).includes('"b"'), 'a digest is kept, not the token')
})
