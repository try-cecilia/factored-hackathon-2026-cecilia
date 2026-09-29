// After a login the browser lands on /operador/ingreso, which sees the cookie the browser kept (or did not) and says so.
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, SAME_ORIGIN, sessionCookie, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())

const arrival = (to: string, cookie?: string) => app.send(`/operador/ingreso?to=${encodeURIComponent(to)}`, { headers: cookie ? { Cookie: cookie } : {} })

describe('the login lands on the arrival check', () => {
  test('a login redirects to it, carrying the target', async () => {
    const res = await app.send('/operador/sesion', { fields: { admin_key: ADMIN, redirect: '/operador/trazas' }, headers: SAME_ORIGIN })
    assert.equal(res.status, 303)
    assert.equal(res.headers.get('location'), `/operador/ingreso?to=${encodeURIComponent('/operador/trazas')}`)
  })

  test('with the session cookie the browser kept, it goes on to the target', async () => {
    const cookie = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: SAME_ORIGIN }))!
    const res = await arrival('/operador/trazas', cookie)
    assert.equal(res.status, 303)
    assert.equal(res.headers.get('location'), '/operador/trazas')
  })

  test('without a cookie (the browser dropped it) it goes back to the login saying why, and sets nothing', async () => {
    const res = await arrival('/operador/trazas')
    assert.equal(res.status, 303)
    assert.equal(res.headers.get('location'), `/operador/login?redirect=${encodeURIComponent('/operador/trazas')}&motivo=sin-cookie`)
    assert.equal(res.headers.getSetCookie().length, 0)
  })

  test('a cookie of a session that no longer exists counts as no session', async () => {
    const res = await arrival('/operador/cola', 'cecilai_operator=gone')
    assert.match(res.headers.get('location') ?? '', /motivo=sin-cookie/)
  })

  test('a target that leaves the site is never followed', async () => {
    const cookie = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: SAME_ORIGIN }))!
    for (const to of ['//evil.example/x', 'https://evil.example', '/\\evil.example', '/%2f/evil.example']) {
      assert.equal((await arrival(to, cookie)).headers.get('location'), '/operador/cola', to)
      assert.match((await arrival(to)).headers.get('location') ?? '', /^\/operador\/login\?redirect=%2Foperador%2Fcola&motivo=sin-cookie$/, to)
    }
  })

  test('the login page shows the message in Spanish, and in Portuguese with the language cookie', async () => {
    const es = await (await app.send('/operador/login?motivo=sin-cookie')).text()
    assert.match(es, /Tu navegador no guardó la sesión/)
    const pt = await (await app.send('/operador/login?motivo=sin-cookie', { headers: { Cookie: 'cecilai_lang=pt' } })).text()
    assert.match(pt, /Seu navegador não guardou a sessão/)
    assert.doesNotMatch(await (await app.send('/operador/login')).text(), /no guardó la sesión/)
  })
})
