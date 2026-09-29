import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, SAME_ORIGIN, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())

const landing = async (redirect: string) => {
  const res = await app.send('/operador/sesion', { fields: { admin_key: ADMIN, redirect }, headers: SAME_ORIGIN })
  assert.equal(res.status, 303)
  return res.headers.get('location')
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
