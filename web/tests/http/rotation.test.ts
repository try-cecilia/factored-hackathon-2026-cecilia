import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, ANA, SAME_ORIGIN, opensConsole, sessionCookie, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())

const post = (path: string, fields: Record<string, string>, cookie?: string) =>
  app.send(path, { fields, headers: { ...SAME_ORIGIN, ...(cookie && { Cookie: cookie }) } })

describe('a session id is never reused when the session gains rights or is replaced', () => {
  test('adding the operator key issues a new id, and the read-only cookie stops working', async () => {
    const readOnly = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
    assert.ok(await opensConsole(app, readOnly))
    const raised = await post('/operador/clave', { operator_key: ANA, redirect: '/operador/cola' }, readOnly)
    assert.equal(raised.status, 303)
    const acting = sessionCookie(raised)
    assert.ok(acting, 'a new cookie is set')
    assert.notEqual(acting, readOnly)
    assert.ok(await opensConsole(app, acting!), 'the new cookie works')
    assert.equal(await opensConsole(app, readOnly), false, 'the copied read-only cookie gained nothing and is dead')
  })

  test('a wrong operator key leaves the session as it was', async () => {
    const readOnly = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
    const refused = await post('/operador/clave', { operator_key: 'nope-nope-nope-nope-nope-nope' }, readOnly)
    assert.equal(sessionCookie(refused), null)
    assert.ok(await opensConsole(app, readOnly))
  })

  test('logging in again from a browser that already has a session ends the old one', async () => {
    const first = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
    const second = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }, first))!
    assert.notEqual(second, first)
    assert.ok(await opensConsole(app, second))
    assert.equal(await opensConsole(app, first), false)
  })

  test('a failed login does not end the session the browser already had', async () => {
    const first = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
    const failed = await post('/operador/sesion', { admin_key: 'wrong' }, first)
    assert.equal(sessionCookie(failed), null)
    assert.ok(await opensConsole(app, first))
  })
})
