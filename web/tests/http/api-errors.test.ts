import assert from 'node:assert/strict'
import { after, before, beforeEach, describe, test } from 'node:test'
import { ADMIN, SAME_ORIGIN, cookieJar, opensConsole, sessionCookie, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())
beforeEach(() => app.setApi('ok'))

const login = (cookie?: string) => app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: { ...SAME_ORIGIN, ...(cookie && { Cookie: cookie }) } })
const touchesSession = (response: Response) => response.headers.getSetCookie().some((c) => /cecilai_operator=/.test(c) && !/flash/.test(c))

describe('what the agent API answers to a read decides the session on the server, never the cookie in the browser', () => {
  test('a 401 (the read key was revoked) ends the session that made the request, and sends no Set-Cookie', async () => {
    const cookie = sessionCookie(await login())!
    app.setApi('revoked')
    const res = await app.send('/operador/cola', { headers: { Cookie: cookie } })
    assert.equal(res.status, 200)
    assert.equal(touchesSession(res), false, res.headers.getSetCookie().join(' | '))
    app.setApi('ok')
    assert.equal(await opensConsole(app, cookie), false, 'the session is gone on the server')
  })

  test('a slow 401 for the old session cannot delete the cookie of the login that replaced it', async () => {
    const old = sessionCookie(await login())!
    const slow = app.hold()
    const pendingRead = app.send('/operador/cola', { headers: { Cookie: old } }) // waits inside the API
    await slow.reached
    const replaced = await login(old) // a new session takes over while the read is still pending
    slow.release(401) // the API finally answers the old read with a 401
    const late = await pendingRead

    const browser = cookieJar()
    const [name, value] = old.split('=')
    browser.apply(new Response(null, { headers: { 'Set-Cookie': `${name}=${value}; Path=/` } }))
    browser.apply(replaced)
    browser.apply(late) // the late answer is applied last, as in the reproduced order
    assert.equal(browser.session(), sessionCookie(replaced), 'the browser keeps the new session')
    assert.ok(await opensConsole(app, browser.session()!), 'and it is still alive on the server')

    const out = await app.send('/operador/salir', { method: 'POST', headers: { ...SAME_ORIGIN, Cookie: browser.header() } })
    browser.apply(out)
    assert.equal(browser.session(), null)
    assert.equal(await opensConsole(app, sessionCookie(replaced)!), false, 'no orphan session is left behind')
  })

  for (const [mode, status] of [['forbidden', 403], ['error', 500]] as const) {
    test(`a ${status} from the API neither ends the session nor touches the cookie`, async () => {
      const cookie = sessionCookie(await login())!
      app.setApi(mode)
      for (const page of ['/operador/cola', '/operador/monitoreo', '/operador/trazas']) {
        const res = await app.send(page, { headers: { Cookie: cookie } })
        assert.equal(res.status, 200, page)
        assert.equal(touchesSession(res), false, page)
      }
      app.setApi('ok')
      assert.ok(await opensConsole(app, cookie), 'the session survived the failing reads')
    })
  }
})
