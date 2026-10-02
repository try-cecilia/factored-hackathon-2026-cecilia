// F1, the web side: signing out is the person's decision, so the browser lets go of the cookie even when the API could not be asked to
// revoke the session (a 500, no answer, a dropped connection). What the person is told is the truth: the revocation was not confirmed.
import assert from 'node:assert/strict'
import { after, before, beforeEach, describe, test } from 'node:test'
import { cookieJar } from './harness.ts'
import { startCustomerApp, TOKEN } from './customer-harness.ts'
import { rpcOutcome } from './rpc.ts'

let app: Awaited<ReturnType<typeof startCustomerApp>>
before(async () => { app = await startCustomerApp((req, reply) => (req.url === '/chat/history' ? reply(200, { turns: [], cases: [] }) : false)) })
after(() => app.close())
beforeEach(() => app.setDelete('ok'))

const SESSION = /cecilai_session$/
const withCookie = (token: string) => ({ Cookie: `cecilai_session=${token}` })
const clearsTheCookie = (response: Response) => response.headers.getSetCookie().some((c) => /^cecilai_session=;/.test(c) && /Max-Age=0/i.test(c))
const opensChat = async (cookie: string) => (await app.fetch(new Request('http://app.test/chat', { headers: { Cookie: cookie }, redirect: 'manual' }))).status === 200

describe('signing out of the customer session', () => {
  test('with the API answering, the session is revoked, the cookie goes and the answer says it was confirmed', async () => {
    app.nextTokens('tok-out-ok-0123456789abcdef')
    const jar = cookieJar(SESSION)
    jar.apply(await app.signIn())
    const out = await app.rpc('logout', { headers: { Cookie: jar.header() } })
    jar.apply(out)
    const answer = await rpcOutcome(out)
    assert.equal(answer.error, undefined)
    assert.deepEqual(answer.result, { revoked: true })
    assert.equal(jar.session(), null)
    assert.equal(app.isLive('tok-out-ok-0123456789abcdef'), false)
  })

  for (const mode of ['error', 'drop', 'hang'] as const) {
    test(`when the API's revocation fails (${mode}), the cookie still goes, nothing internal is sent, and the revocation is not presented as confirmed`, async () => {
      app.setDelete(mode)
      const jar = cookieJar(SESSION)
      jar.apply(new Response(null, { headers: { 'Set-Cookie': `cecilai_session=${TOKEN}; Path=/` } }))
      const out = await app.rpc('logout', { headers: { Cookie: jar.header() } })
      assert.ok(clearsTheCookie(out), `no deletion in: ${out.headers.getSetCookie().join(' | ')}`)
      jar.apply(out)
      const answer = await rpcOutcome(out)
      assert.equal(answer.error, undefined, 'the failure is an answer, not a thrown error')
      assert.deepEqual(answer.result, { revoked: false })
      assert.doesNotMatch(answer.text, /agent API|500|timeout|ECONN|fetch failed/i)
      assert.equal(jar.session(), null)
      assert.equal(await opensChat(jar.header()), false, 'the browser no longer reaches the chat')
    })
  }

  test('without a cookie there is nothing to revoke and nothing to ask the API', async () => {
    const before = app.seen.length
    const answer = await rpcOutcome(await app.rpc('logout'))
    assert.deepEqual(answer.result, { revoked: true })
    assert.equal(app.seen.length, before)
  })

  test('a login that replaced the cookie meanwhile keeps its cookie: the sign-out that was waiting on the API does not delete it', async () => {
    for (const order of ['logout first', 'logout last'] as const) {
      app.nextTokens(`tok-new-${order.replace(' ', '-')}-0123456789`)
      const stale = withCookie(TOKEN)
      const slow = app.hold((req) => req.method === 'DELETE' && req.headers['x-session-token'] === TOKEN)
      const signingOut = app.rpc('logout', { headers: stale }) // waits inside the API
      await slow.reached
      const replaced = await app.signIn(undefined, undefined, stale) // another tab signs in again over the same cookie
      slow.release(500) // the API finally fails the revocation of the old token
      const out = await signingOut

      const jar = cookieJar(SESSION)
      jar.apply(new Response(null, { headers: { 'Set-Cookie': `cecilai_session=${TOKEN}; Path=/` } }))
      const responses = order === 'logout first' ? [out, replaced] : [replaced, out]
      for (const response of responses) jar.apply(response)
      const kept = jar.session()
      assert.ok(kept && !kept.endsWith(TOKEN), `${order}: the browser keeps the new session, has ${kept}`)
      assert.ok(await opensChat(jar.header()), `${order}: and it opens the chat`)
      assert.deepEqual((await rpcOutcome(out)).result, { revoked: false }, order)
    }
  })
})
