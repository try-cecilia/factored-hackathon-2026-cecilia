import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, ANA, SAME_ORIGIN, cookieJar, opensConsole, sessionCookie, startConsole } from './harness.ts'

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

  test('the loser of that race only redirects with a notice: it never touches the session cookie', async () => {
    const old = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
    const answers = await Promise.all([post('/operador/sesion', { admin_key: ADMIN }, old), post('/operador/sesion', { admin_key: ADMIN }, old)])
    const loser = answers.find((r) => sessionCookie(r) === null)!
    assert.equal(loser.status, 303)
    assert.equal(loser.headers.get('location'), '/operador/login')
    const lines = loser.headers.getSetCookie()
    assert.ok(lines.some((c) => /flash=session_replaced/.test(c)))
    assert.ok(lines.every((c) => /flash=/.test(c)), `only the notice is set, not the session cookie: ${lines.join(' | ')}`)
  })

  for (const order of ['winner first', 'loser first'] as const) {
    test(`whichever response the browser applies last (${order}), it ends with the winning session, and logout leaves none`, async () => {
      for (let round = 0; round < 5; round++) {
        const old = sessionCookie(await post('/operador/sesion', { admin_key: ADMIN }))!
        const answers = await Promise.all([post('/operador/sesion', { admin_key: ADMIN }, old), post('/operador/sesion', { admin_key: ADMIN }, old)])
        const winner = answers.find((r) => sessionCookie(r) !== null)!
        const loser = answers.find((r) => sessionCookie(r) === null)!
        const browser = cookieJar()
        // The browser starts with the old cookie, as it did when it sent both requests.
        const [oldName, oldValue] = old.split('=')
        browser.apply(new Response(null, { headers: { 'Set-Cookie': `${oldName}=${oldValue}; Path=/` } }))
        for (const response of order === 'winner first' ? [winner, loser] : [loser, winner]) browser.apply(response)

        assert.equal(browser.session(), sessionCookie(winner), 'the browser holds the winning session')
        assert.ok(await opensConsole(app, browser.session()!))
        const out = await app.send('/operador/salir', { method: 'POST', headers: { ...SAME_ORIGIN, Cookie: browser.header() } })
        assert.equal(out.status, 303)
        browser.apply(out)
        assert.equal(browser.session(), null)
        assert.equal(await opensConsole(app, sessionCookie(winner)!), false, 'no orphan session survives the logout')
        assert.equal(await opensConsole(app, old), false)
      }
    })
  }
})
