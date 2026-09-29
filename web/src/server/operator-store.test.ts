import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ABSOLUTE_MS, IDLE_MS, MAX_SESSIONS, SessionStore } from './operator-store.ts'

const MIN = 60_000
function clock() {
  let at = 1_000_000
  return { now: () => at, advance: (ms: number) => void (at += ms) }
}

test('an abandoned console expires 30 minutes after the last person-made request, however much it refreshes itself', () => {
  const time = clock()
  const store = new SessionStore(time.now)
  const id = store.start('admin-key')
  let polls = 0
  // What was reproduced in review: the tab refreshes every 30 s for 31 minutes and used to stay alive for good.
  for (let elapsed = 0; elapsed < 31 * MIN; elapsed += 30_000) {
    time.advance(30_000)
    polls += 1
    if (store.lookup(id, false).status === 'expired') break
  }
  assert.ok(polls >= 60, `only ${polls} polls`)
  assert.equal(store.lookup(id, false).status, 'unknown', 'the expired session is gone')
  assert.equal(IDLE_MS, 30 * MIN)
})

test('a background read neither renews the session nor is refused before the deadline', () => {
  const time = clock()
  const store = new SessionStore(time.now)
  const id = store.start('admin-key', 'op-key', 'ana')
  time.advance(29 * MIN)
  const seen = store.lookup(id, false)
  assert.equal(seen.status, 'active')
  assert.equal(seen.status === 'active' && seen.session.lastSeen, 1_000_000, 'lastSeen unchanged by the poll')
  time.advance(2 * MIN) // 31 minutes since the person was last there
  assert.equal(store.lookup(id, false).status, 'expired')
})

test('a person-made request (a click, a navigation, an action) renews the idle window', () => {
  const time = clock()
  const store = new SessionStore(time.now)
  const id = store.start('admin-key')
  for (let i = 0; i < 10; i++) {
    time.advance(20 * MIN)
    assert.equal(store.lookup(id, true).status, 'active')
  }
})

test('the 8-hour cap holds even for someone who never stops clicking', () => {
  const time = clock()
  const store = new SessionStore(time.now)
  const id = store.start('admin-key')
  let status = 'active'
  for (let elapsed = 0; elapsed <= ABSOLUTE_MS; elapsed += 10 * MIN) {
    time.advance(10 * MIN)
    status = store.lookup(id, true).status
    if (status !== 'active') break
  }
  assert.equal(status, 'expired')
})

test('a cookie for a session that is not there (restart, logout) is unknown, not expired', () => {
  const store = new SessionStore()
  assert.equal(store.lookup('nope', true).status, 'unknown')
  assert.equal(store.lookup(undefined, true).status, 'unknown')
  const id = store.start('admin-key')
  store.end(id)
  assert.equal(store.lookup(id, true).status, 'unknown')
})

test('the store is bounded and drops the idle sessions first', () => {
  const time = clock()
  const store = new SessionStore(time.now)
  const first = store.start('admin-key')
  time.advance(IDLE_MS + MIN)
  for (let i = 0; i < MAX_SESSIONS + 5; i++) store.start(`key-${i}`)
  assert.equal(store.lookup(first, true).status, 'unknown')
})

test('raising a session gives it a new id, keeps the original cap and kills the old id', () => {
  const time = clock()
  const store = new SessionStore(time.now, ABSOLUTE_MS) // idle window out of the way: this test is about the cap
  const readOnly = store.start('admin-key')
  time.advance(7 * 60 * MIN)
  const acting = store.elevate(readOnly, 'op-key', 'ana')!
  assert.ok(acting && acting !== readOnly)
  assert.equal(store.lookup(readOnly, false).status, 'unknown', 'the id that may have been copied gains nothing')
  const now = store.lookup(acting, false)
  assert.ok(now.status === 'active' && now.session.operator === 'ana' && now.session.adminKey === 'admin-key')
  time.advance(61 * MIN) // 8 h 1 min since the original login: elevating did not restart the cap
  assert.equal(store.lookup(acting, false).status, 'expired')
})

test('a session that is gone cannot be raised', () => {
  const store = new SessionStore()
  assert.equal(store.elevate('nope', 'op-key'), null)
  assert.equal(store.elevate(undefined, 'op-key'), null)
})

test('taking a session is atomic: the first caller gets it, the second is told it was already taken', () => {
  const store = new SessionStore()
  const id = store.start('admin-key')
  assert.equal(store.take(id), 'taken')
  assert.equal(store.take(id), 'already')
  assert.equal(store.lookup(id, false).status, 'unknown')
  assert.equal(store.take('never-existed'), 'none')
  assert.equal(store.take(undefined), 'none')
})

test('a session that had expired is not "taken": its holder just logs in again', () => {
  const time = clock()
  const store = new SessionStore(time.now)
  const id = store.start('admin-key')
  time.advance(IDLE_MS + MIN)
  assert.equal(store.take(id), 'none')
})

test('the memory of consumed ids is short and bounded', () => {
  const time = clock()
  const store = new SessionStore(time.now)
  const id = store.start('admin-key')
  assert.equal(store.take(id), 'taken')
  time.advance(6 * MIN)
  assert.equal(store.take(id), 'none', 'after the race window an old cookie is only an unknown one')
  for (let i = 0; i < 3000; i++) store.take(store.start(`key-${i}`))
  assert.equal(store.take(id), 'none')
})
