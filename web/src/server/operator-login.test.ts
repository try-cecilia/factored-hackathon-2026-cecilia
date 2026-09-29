import assert from 'node:assert/strict'
import { test } from 'node:test'
import { loginFromForm, operatorKeyFromForm, type KeyProbe } from './operator-login.ts'

const ADMIN = 'admin-key-0123456789-abcdefgh'
const ANA = 'ana-key-0123456789-abcdefghij'

const form = (fields: Record<string, string>) => {
  const data = new FormData()
  for (const [name, value] of Object.entries(fields)) data.set(name, value)
  return data
}
const accepts = (keys: Record<string, unknown>): KeyProbe => async (key) => (key in keys ? { ok: true, data: keys[key] } : { ok: false, status: 401 })
const probes = { admin: accepts({ [ADMIN]: {} }), operator: accepts({ [ANA]: { operator: 'ana' } }) }

test('a read key alone opens a read-only session and lands on the queue', async () => {
  const out = await loginFromForm(form({ admin_key: ADMIN }), probes)
  assert.deepEqual(out, { ok: true, to: '/operador/cola', keys: { adminKey: ADMIN } })
})

test('the operator key is stored with the name the API gave it', async () => {
  const out = await loginFromForm(form({ admin_key: ADMIN, operator_key: ANA }), probes)
  assert.equal(out.ok && out.keys.operator, 'ana')
})

test('a rejected key sends the browser back with a fixed code, never with what was typed', async () => {
  const wrongAdmin = await loginFromForm(form({ admin_key: 'SECRET-WRONG-ADMIN', operator_key: ANA }), probes)
  const wrongOperator = await loginFromForm(form({ admin_key: ADMIN, operator_key: 'SECRET-WRONG-OPERATOR' }), probes)
  assert.deepEqual([wrongAdmin.ok, wrongOperator.ok], [false, false])
  assert.equal(!wrongAdmin.ok && wrongAdmin.flash, 'admin_401')
  assert.equal(!wrongOperator.ok && wrongOperator.flash, 'operator_401')
  for (const out of [wrongAdmin, wrongOperator]) {
    const visible = JSON.stringify({ to: out.to, flash: !out.ok && out.flash })
    assert.doesNotMatch(visible, /SECRET|admin-key|ana-key/)
  }
})

test('nothing the browser receives (redirect or flash) contains a key, even on success', async () => {
  const out = await loginFromForm(form({ admin_key: ADMIN, operator_key: ANA, redirect: '/operador/monitoreo' }), probes)
  assert.ok(out.ok)
  assert.equal(out.to, '/operador/monitoreo')
  assert.ok(!out.to.includes(ADMIN) && !out.to.includes(ANA))
})

test('the operator key is not even checked when the read key is wrong', async () => {
  let asked = false
  const spy: KeyProbe = async () => ((asked = true), { ok: true, data: {} })
  await loginFromForm(form({ admin_key: 'nope', operator_key: ANA }), { admin: accepts({}), operator: spy })
  assert.equal(asked, false)
})

test('a missing read key and an oversized key are refused before any request', async () => {
  const boom: KeyProbe = async () => assert.fail('the API must not be asked')
  const none = await loginFromForm(form({ operator_key: ANA }), { admin: boom, operator: boom })
  const long = await loginFromForm(form({ admin_key: 'x'.repeat(201) }), { admin: boom, operator: boom })
  assert.equal(!none.ok && none.flash, 'admin_missing')
  assert.equal(!long.ok && long.flash, 'key_invalid')
})

test('the redirect target must be a path on this site', async () => {
  for (const evil of ['https://evil.example/x', '//evil.example', '/\\evil.example', 'javascript:alert(1)']) {
    const out = await loginFromForm(form({ admin_key: ADMIN, redirect: evil }), probes)
    assert.ok(out.ok && out.to === '/operador/cola', evil)
  }
  const failed = await loginFromForm(form({ admin_key: 'no', redirect: '/operador/trazas' }), probes)
  assert.equal(failed.to, '/operador/login?redirect=%2Foperador%2Ftrazas')
})

test('adding an operator key to a read-only session returns the owner and goes back to the page', async () => {
  const ok = await operatorKeyFromForm(form({ operator_key: ANA, redirect: '/operador/cola/abc' }), probes.operator)
  assert.deepEqual(ok, { ok: true, to: '/operador/cola/abc', operatorKey: ANA, operator: 'ana' })
  const bad = await operatorKeyFromForm(form({ operator_key: 'SECRET-NOPE', redirect: '/operador/cola/abc' }), probes.operator)
  assert.deepEqual(bad, { ok: false, to: '/operador/cola/abc', flash: 'operator_401' })
})
