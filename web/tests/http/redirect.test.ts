import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, SAME_ORIGIN, sessionCookie, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())

const landing = async (redirect: string) => {
  const res = await app.send('/operador/sesion', { fields: { admin_key: ADMIN, redirect }, headers: SAME_ORIGIN })
  assert.equal(res.status, 303)
  // The login lands on the arrival check first (operador.ingreso.ts), which carries the target it will send the operator on to.
  const arrival = new URL(res.headers.get('location') ?? '', 'http://console.test')
  assert.equal(arrival.pathname, '/operador/ingreso')
  return arrival.searchParams.get('to')
}

describe('the redirect after login never leaves this site', () => {
  const evil = [
    'https://evil.example/x', '//evil.example/x', '/\\evil.example/x', 'javascript:alert(1)',
    '/.//evil.example/x', '/a/..//evil.example/x', '/%2e//evil.example/x', '/%2E/%2e//evil.example/x', '/./\\evil.example',
    '/%2f/evil.example/x', '/%2F/evil.example/x', '/%5cevil.example/x', '/%5Cevil.example/x', '/a/%5c..%5c/evil.example',
    '/\t/evil.example/x', '/\n/evil.example/x', '/\r/evil.example/x', '/%09/evil.example/x', '/%0a/evil.example/x', '/\u0000/evil.example',
    '/%252f/../..//evil.example', '/x/../../..//evil.example',
  ]
  for (const target of evil) {
    test(`refuses ${JSON.stringify(target)}`, async () => {
      const to = await landing(target)
      assert.equal(to, '/operador/cola')
      assert.ok(!to!.startsWith('//'))
    })
  }

  test('a real console path, with its query, is kept, and dot segments are normalised', async () => {
    assert.equal(await landing('/operador/monitoreo?x=1'), '/operador/monitoreo?x=1')
    assert.equal(await landing('/operador/./trazas/../cola/8e60583f'), '/operador/cola/8e60583f')
  })

  test('a failed login sends the browser back with only a safe target', async () => {
    const bad = await app.send('/operador/sesion', { fields: { admin_key: 'nope', redirect: '/.//evil.example/x' }, headers: SAME_ORIGIN })
    assert.equal(bad.headers.get('location'), '/operador/login')
  })
})

describe('the login page, visited while already signed in, never bounces out of the site', () => {
  // The router may first drop an invalid query string (a 307 to the bare login page) before the signed-in redirect: follow
  // the hops and judge where the browser ends up, which is what matters.
  const visit = async (query: string) => {
    const cookie = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: SAME_ORIGIN }))!
    let res = await app.send(`/operador/login${query}`, { headers: { Cookie: cookie } })
    for (let hops = 0; hops < 4 && res.status >= 300 && res.status < 400; hops++) {
      const to = res.headers.get('location')!
      assert.ok(to.startsWith('/') && !to.startsWith('//'), `left the site: ${to}`)
      const next = await app.send(to, { headers: { Cookie: cookie } })
      if (next.status < 300 || next.status >= 400) return res
      res = next
    }
    return res
  }

  for (const hostile of ['//evil.example/x', '/.//evil.example/x', '/%2f/evil.example', '/%5cevil.example', 'https://evil.example']) {
    test(`?redirect=${hostile} goes to the queue`, async () => {
      const res = await visit(`?redirect=${encodeURIComponent(hostile)}`)
      assert.equal(res.status, 307)
      assert.equal(res.headers.get('location'), '/operador/cola')
    })
  }

  test('a real target is honoured', async () => {
    const res = await visit(`?redirect=${encodeURIComponent('/operador/trazas')}`)
    assert.equal(res.headers.get('location'), '/operador/trazas')
  })
})
