import assert from 'node:assert/strict'
import { test } from 'node:test'
import { demoEntries, entriesOf, parseRole } from './demo-entry.ts'
import { demoConsoleOn } from './demo-gate.ts'
import { createLimiter, perMinuteFromEnv } from './demo-limit.ts'

const scenario = (id: string, customer_id: string, language = 'es') => ({ id, customer_id, language })

test('the dialog offers the roles whose scenario the API lists, in its own order', () => {
  const all = [scenario('normal_pt_arrears', 'C3', 'pt'), scenario('other', 'C9'), scenario('normal_balance', 'C1')]
  assert.deepEqual(entriesOf(all), [{ role: 'cuentas', customer_id: 'C1', language: 'es' }, { role: 'portugues', customer_id: 'C3', language: 'pt' }])
  assert.deepEqual(entriesOf([]), [])
})

test('a role is one of the three, nothing else', () => {
  assert.deepEqual(parseRole({ role: 'pendiente' }), { role: 'pendiente' })
  for (const role of [undefined, '', 'admin', 'normal_balance', 1]) assert.throws(() => parseRole({ role }), /role is not valid/)
})

test('the kit offers entries only with the console on: fail-closed', () => {
  const entries = [{ role: 'cuentas' as const, customer_id: 'C1', language: 'es' }]
  assert.deepEqual(demoEntries({ enabled: true, console: true, entries }), entries)
  assert.deepEqual(demoEntries({ enabled: true, entries }), [])
  assert.deepEqual(demoEntries({ enabled: true, console: false, entries }), [])
  assert.deepEqual(demoEntries({ enabled: false }), [])
})

test('the demo console needs DEMO_MODE and DEMO_CONSOLE exactly "1"', () => {
  assert.equal(demoConsoleOn({ DEMO_MODE: '1', DEMO_CONSOLE: '1' }), true)
  for (const env of [{}, { DEMO_CONSOLE: '1' }, { DEMO_MODE: '1' }, { DEMO_MODE: '1', DEMO_CONSOLE: 'true' }, { DEMO_MODE: '1', DEMO_CONSOLE: ' 1' },
    { DEMO_MODE: 'yes', DEMO_CONSOLE: '1' }, { DEMO_MODE: '0', DEMO_CONSOLE: '1' }, { DEMO_MODE: '1', DEMO_CONSOLE: '0' }]) {
    assert.equal(demoConsoleOn(env), false, JSON.stringify(env))
  }
})

test('entering is limited per address in a sliding minute, and a refused try does not count', () => {
  const limiter = createLimiter(() => 3)
  for (let i = 0; i < 3; i++) assert.deepEqual(limiter.take('1.1.1.1', 1_000 + i), { ok: true })
  const refused = limiter.take('1.1.1.1', 2_000)
  assert.equal(refused.ok, false)
  assert.equal(!refused.ok && refused.retryAfter, 59)
  assert.deepEqual(limiter.take('2.2.2.2', 2_000), { ok: true }, 'another address has its own window')
  assert.deepEqual(limiter.take('1.1.1.1', 61_001), { ok: true }, 'the first entry left the window')
  assert.equal(perMinuteFromEnv(undefined), 10)
  assert.equal(perMinuteFromEnv('0'), 10)
  assert.equal(perMinuteFromEnv('4'), 4)
})
