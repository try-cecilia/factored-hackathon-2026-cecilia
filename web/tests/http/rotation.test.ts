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

  test('two simultaneous logins with the same cookie leave at most one valid replacement, and logging out ends it', async () => {
    for (let round = 0; round < 5; round++) {
      const old = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
      const answers = await Promise.all([post('/operador/sesion', { admin_key: ADMIN }, old), post('/operador/sesion', { admin_key: ADMIN }, old)])
      const cookies = answers.map(sessionCookie).filter((c): c is string => c !== null)
      assert.ok(cookies.length <= 1, `round ${round}: ${cookies.length} replacements were issued`)
      assert.equal(await opensConsole(app, old), false, 'the consumed cookie is dead')
      const [replacement] = cookies
      if (!replacement) continue
      assert.ok(await opensConsole(app, replacement))
      const out = await app.send('/operador/salir', { method: 'POST', headers: { ...SAME_ORIGIN, Cookie: replacement } })
      assert.equal(out.status, 303)
      assert.equal(await opensConsole(app, replacement), false, 'after logout nothing from that login is left')
    }
  })

  test('the loser of that race is sent back to the login with a message, and the stale cookie is cleared so a retry works', async () => {
    const old = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
    const [first, second] = await Promise.all([post('/operador/sesion', { admin_key: ADMIN }, old), post('/operador/sesion', { admin_key: ADMIN }, old)])
    const loser = sessionCookie(first) ? second : first
    assert.equal(loser.status, 303)
    assert.equal(loser.headers.get('location'), '/operador/login')
    assert.ok(loser.headers.getSetCookie().some((c) => /flash=session_replaced/.test(c)))
    const retry = await post('/operador/sesion', { admin_key: ADMIN }) // the browser dropped the cleared cookie
    assert.ok(sessionCookie(retry))
  })
})
