// The customer login, visited with a live session, sends the browser on to the page it came from, and only ever to a page of this site.
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ORIGIN, startCustomerApp, TOKEN } from './customer-harness.ts'

let app: Awaited<ReturnType<typeof startCustomerApp>>
before(async () => { app = await startCustomerApp(() => false) })
after(() => app.close())

const cookie = { Cookie: `cecilai_session=${TOKEN}` }
// The router may first drop an invalid query string (a 307 to the bare login page) before the signed-in redirect: follow the
// hops, judge every one of them, and return where the browser ends up.
const visit = async (redirect: string) => {
  let res = await app.get(`/login?redirect=${redirect}`, cookie)
  for (let hops = 0; hops < 4 && res.status >= 300 && res.status < 400; hops++) {
    const to = res.headers.get('location') ?? ''
    assert.equal(new URL(to, ORIGIN).origin, ORIGIN, `left the site: ${to}`)
    assert.ok(to.startsWith('/') && !to.startsWith('//'), `not a path of this site: ${to}`)
    const next = await app.get(to, cookie)
    if (next.status < 300 || next.status >= 400) return res
    res = next
  }
  return res
}

describe('the login page, visited while signed in, never sends the customer to another site', () => {
  const hostile: [string, string][] = [
    ['an absolute external URL', 'https://evil.invalid'],
    ['a protocol-relative URL', '//evil.invalid'],
    ['a backslash host', '/\\evil.invalid'],
    ['a javascript: scheme', 'javascript:alert(1)'],
    ['a percent-encoded protocol-relative URL', '%2F%2Fevil.invalid'],
    ['a double percent-encoded slash', '/%252f/evil.invalid'],
    ['a double percent-encoded host', 'https%253A%252F%252Fevil.invalid'],
    ['an encoded backslash', '/%5cevil.invalid'],
    ['dot segments that collapse to a host', '/a/..//evil.invalid'],
    ['a path of this site that is no page (userinfo look-alike)', '/@evil.invalid'],
    ['a path of this site that is no page', '/nada'],
    ['a page of the console, which is not the customer\'s', '/operador/cola'],
    ['a page of the customer app that is not a destination', '/login'],
  ]
  for (const [name, value] of hostile) {
    test(`${name} (${value}) goes to the chat`, async () => {
      const res = await visit(encodeURIComponent(value))
      assert.equal(res.status, 307, `${res.status} ${res.headers.get('location')}`)
      assert.equal(res.headers.get('location'), '/chat')
    })
    test(`${name} (${value}), sent raw as a browser may, goes to the chat and never answers 500`, async () => {
      const res = await visit(value)
      assert.equal(res.status, 307, `${res.status} ${res.headers.get('location')}`)
      assert.equal(res.headers.get('location'), '/chat')
    })
  }

  test('a real target, with its query and fragment, is kept (with a trailing slash too)', async () => {
    assert.equal((await visit(encodeURIComponent('/chat/?x=1'))).headers.get('location'), '/chat?x=1')
  })

  test('a real target, with its query and fragment, is kept', async () => {
    const res = await visit(encodeURIComponent('/chat?x=1#foo'))
    assert.equal(res.status, 307)
    assert.equal(res.headers.get('location'), '/chat?x=1#foo')
  })
})
