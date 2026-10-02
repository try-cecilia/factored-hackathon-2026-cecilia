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

  // The policy: leaving removes the cookie of THIS browser, always. The server cannot tell a login of another tab whose answer arrived
  // from one whose answer was lost, and the second must not keep the person signed in. The cost is stated: a concurrent login that did
  // reach the browser is closed there too (the person signs in again), and its token stays valid in the API until it expires.
  test('a login of another tab that finished while the sign-out waited is closed in the browser too, and its token stays valid in the API', async () => {
    const old = 'tok-policy-old-0123456789'
    const fresh = 'tok-policy-new-0123456789'
    app.nextTokens(old)
    await app.signIn()
    app.nextTokens(fresh)
    const stale = withCookie(old)
    const slow = app.hold((req) => req.method === 'DELETE' && req.headers['x-session-token'] === old)
    const signingOut = app.rpc('logout', { headers: stale })
    await slow.reached
    const replaced = await app.signIn(undefined, undefined, stale) // delivered to the browser
    slow.release(500)
    const out = await signingOut
    assert.ok(clearsTheCookie(out), 'the sign-out removes the cookie whatever happened meanwhile')

    const jar = cookieJar(SESSION)
    jar.apply(new Response(null, { headers: { 'Set-Cookie': `cecilai_session=${old}; Path=/` } }))
    for (const response of [replaced, out]) jar.apply(response)
    assert.equal(jar.session(), null, 'the browser holds no session: the person signs in again')
    assert.equal(app.isLive(fresh), true, 'the concurrent login stays valid in the API until it expires')
    assert.deepEqual((await rpcOutcome(out)).result, { revoked: false })
  })

  // A login whose answer is lost DURING the wait: the browser still holds the cookie the request carried, and it must go.
  test('a login whose response is lost while the sign-out waits does not keep the old cookie alive', async () => {
    const old = 'tok-lost-during-old-0123456789'
    app.nextTokens(old)
    const jar = cookieJar(SESSION)
    jar.apply(await app.signIn())
    app.nextTokens('tok-lost-during-new-0123456789')
    const slow = app.hold((req) => req.method === 'DELETE' && req.headers['x-session-token'] === old)
    const signingOut = app.rpc('logout', { headers: { Cookie: jar.header() } })
    await slow.reached
    await app.signIn(undefined, undefined, { Cookie: jar.header() }) // the answer is dropped on the way
    slow.release(500)
    const out = await signingOut
    assert.ok(clearsTheCookie(out), `no deletion in: ${out.headers.getSetCookie().join(' | ')}`)
    jar.apply(out)
    assert.equal(jar.session(), null)
    assert.equal(await opensChat(`cecilai_session=${old}`), true, 'the revocation was not confirmed: the old token lives until it expires')
  })

  // The other way round: the API issued a new token, but its answer never reached the browser (the connection dropped), so the browser
  // still holds the old cookie. Nothing replaced it there, so signing out must still remove it, whatever the DELETE does.
  for (const mode of ['error', 'ok'] as const) {
    test(`a login whose response was lost does not stop the sign-out from removing the cookie the browser still holds (DELETE ${mode})`, async () => {
      const old = `tok-lost-old-${mode}-0123456789`
      app.nextTokens(old, `tok-lost-new-${mode}-0123456789`)
      const jar = cookieJar(SESSION)
      jar.apply(await app.signIn())
      assert.equal(jar.session(), `cecilai_session=${old}`)
      await app.signIn(undefined, undefined, { Cookie: jar.header() }) // the answer is dropped on the way: never applied to the jar
      app.setDelete(mode)
      const out = await app.rpc('logout', { headers: { Cookie: jar.header() } })
      assert.ok(clearsTheCookie(out), `no deletion in: ${out.headers.getSetCookie().join(' | ')}`)
      jar.apply(out)
      assert.equal(jar.session(), null)
      assert.equal(await opensChat(`cecilai_session=${old}`), mode === 'ok' ? false : true, 'the old token is revoked only when the API says so')
    })
  }
})
