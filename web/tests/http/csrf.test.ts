import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, ANA, assertRefused, CROSS_SITE, ORIGIN, SAME_ORIGIN, sessionCookie, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())

const login = { admin_key: ADMIN }

describe('the operator forms refuse a post that did not come from this site', () => {
  test('a cross-site login is refused (back to the login with a notice, not a bare 403) and starts no session', async () => {
    const res = await app.send('/operador/sesion', { fields: login, headers: CROSS_SITE })
    assertRefused(res, 'origin_refused')
  })

  test('each signal alone is enough to refuse', async () => {
    const refused: Record<string, string>[] = [
      { 'Sec-Fetch-Site': 'cross-site' },
      { 'Sec-Fetch-Site': 'same-site' }, // a sibling subdomain is not this origin
      { 'Sec-Fetch-Site': 'none' },
      { Origin: 'https://attacker.invalid' },
      { Origin: 'null' },
      { Origin: `${ORIGIN}.attacker.invalid` },
      { Referer: 'https://attacker.invalid/operador/login' },
      { 'Sec-Fetch-Site': 'same-origin', Origin: 'https://attacker.invalid' }, // a lying pair is still a mismatch
      {}, // neither header: no proof, no session
    ]
    for (const headers of refused) {
      const res = await app.send('/operador/sesion', { fields: login, headers })
      assertRefused(res, 'origin_refused', JSON.stringify(headers))
    }
  })

  test('the same form from this origin works, with Fetch Metadata, with Origin alone or with Referer alone', async () => {
    const accepted: Record<string, string>[] = [
      SAME_ORIGIN,
      { Origin: ORIGIN },
      { Referer: `${ORIGIN}/operador/login` },
      { 'Sec-Fetch-Site': 'same-origin' },
    ]
    for (const headers of accepted) {
      const res = await app.send('/operador/sesion', { fields: login, headers })
      assert.equal(res.status, 303, JSON.stringify(headers))
      assert.ok(sessionCookie(res), JSON.stringify(headers))
    }
  })

  test('a cross-site add-key post cannot raise a session, and a cross-site logout cannot end one', async () => {
    const cookie = sessionCookie(await app.send('/operador/sesion', { fields: login, headers: SAME_ORIGIN }))!
    const add = await app.send('/operador/clave', { fields: { operator_key: ANA }, headers: { ...CROSS_SITE, Cookie: cookie } })
    assertRefused(add, 'origin_refused')
    const out = await app.send('/operador/salir', { method: 'POST', headers: { ...CROSS_SITE, Cookie: cookie } })
    assertRefused(out, 'origin_refused')
    const still = await app.send('/operador/cola', { headers: { Cookie: cookie } })
    assert.equal(still.status, 200, 'the session survived the cross-site logout')
  })

  test('same-origin add-key and logout still work', async () => {
    const cookie = sessionCookie(await app.send('/operador/sesion', { fields: login, headers: SAME_ORIGIN }))!
    const add = await app.send('/operador/clave', { fields: { operator_key: ANA, redirect: '/operador/cola' }, headers: { ...SAME_ORIGIN, Cookie: cookie } })
    assert.equal(add.status, 303)
    const out = await app.send('/operador/salir', { method: 'POST', headers: { ...SAME_ORIGIN, Cookie: sessionCookie(add) ?? cookie } })
    assert.equal(out.status, 303)
    assert.equal(out.headers.get('location'), '/operador/login')
  })
})
