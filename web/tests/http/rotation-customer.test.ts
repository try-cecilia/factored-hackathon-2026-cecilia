// F8: a late answer about the OLD session token must not take the cookie of a login that has already replaced it. The customer's
// passive reads (session, history, case, chat) treat a rejected token as "no session" and leave the cookie alone: only a login
// overwrites it, and only an explicit sign-out removes it (the operator's console does the same, see rotation.test.ts).
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import type { IncomingMessage } from 'node:http'
import { cookieJar } from './harness.ts'
import { startCustomerApp, TOKEN } from './customer-harness.ts'
import { rpcOutcome } from './rpc.ts'

let app: Awaited<ReturnType<typeof startCustomerApp>>
before(async () => {
  app = await startCustomerApp((req, reply) => {
    if (req.url === '/chat/history') return reply(200, { turns: [], cases: [] })
    return false
  })
})
after(() => app.close())

const SESSION = /cecilai_session$/
const touchesCookie = (response: Response) => response.headers.getSetCookie().some((c) => /cecilai_session=/.test(c))
const opensChat = async (cookie: string) => (await app.fetch(new Request('http://app.test/chat', { headers: { Cookie: cookie }, redirect: 'manual' }))).status === 200

type Late = { name: string; hold: (req: IncomingMessage) => boolean; status: number; body?: unknown; call: (headers: Record<string, string>) => Promise<Response> }
// The chat turn carries the token in its body, not in a header: one turn at a time per token, so the url says which it is.
const withToken = (req: IncomingMessage, prefix: string, method = 'GET') => req.url?.startsWith(prefix) === true && req.method === method && req.headers['x-session-token'] === TOKEN
const lates: Late[] = [
  { name: 'the session read (401)', hold: (r) => withToken(r, '/auth/session'), status: 401, call: (headers) => app.rpc('getSession', { method: 'GET', headers }) },
  { name: 'the history read (401)', hold: (r) => withToken(r, '/chat/history'), status: 401, call: (headers) => app.rpc('getHistory', { method: 'GET', headers }) },
  { name: 'the case read (401)', hold: (r) => withToken(r, '/case/'), status: 401, call: (headers) => app.rpc('getCase', { method: 'GET', data: { ticket_id: 'TKT-0001-ABCD' }, headers }) },
  { name: 'a chat turn (401)', hold: (r) => r.url === '/chat' && r.method === 'POST', status: 401, call: (headers) => app.rpc('sendMessage', { data: { message: 'hola', key: 'key-0123456789' }, headers }) },
  { name: 'a chat turn (REAUTH_REQUIRED)', hold: (r) => r.url === '/chat' && r.method === 'POST', status: 200, body: { disposition: 'REAUTH_REQUIRED' }, call: (headers) => app.rpc('sendMessage', { data: { message: 'hola', key: 'key-0123456789' }, headers }) },
]

describe('a late answer for the old token cannot delete the cookie of the login that replaced it', () => {
  for (const late of lates) {
    for (const order of ['late answer last', 'late answer first'] as const) {
      test(`${late.name}, ${order}`, async () => {
        const fresh = `tok-fresh-${late.name.replace(/\W+/g, '-')}-${order.replace(/\W+/g, '-')}-0123456789`
        app.nextTokens(fresh)
        const old = { Cookie: `cecilai_session=${TOKEN}` }
        const slow = app.hold(late.hold)
        const pending = late.call(old) // waits inside the API with the old token
        await slow.reached
        const replaced = await app.signIn(undefined, undefined, old) // a login takes over while the read is pending
        slow.release(late.status, late.body ?? { detail: 'invalid or expired session' })
        const lateAnswer = await pending

        const browser = cookieJar(SESSION)
        browser.apply(new Response(null, { headers: { 'Set-Cookie': `cecilai_session=${TOKEN}; Path=/` } }))
        for (const response of order === 'late answer last' ? [replaced, lateAnswer] : [lateAnswer, replaced]) browser.apply(response)
        assert.equal(browser.session(), `cecilai_session=${fresh}`, 'the browser keeps the new session')
        assert.equal(touchesCookie(lateAnswer), false, lateAnswer.headers.getSetCookie().join(' | '))
        assert.ok(await opensChat(browser.header()), 'and it opens the chat')
        const out = await app.rpc('logout', { headers: { Cookie: browser.header() } })
        browser.apply(out)
        assert.equal(app.isLive(fresh), false, 'its sign-out revokes the new token')
        assert.equal(browser.session(), null)
      })
    }
  }

  test('a rejected token is "no session", whatever the read: the page goes to sign in and the cookie is left for the next login to overwrite', async () => {
    const dead = { Cookie: 'cecilai_session=tok-dead-0123456789' }
    const page = await app.fetch(new Request('http://app.test/chat', { headers: dead, redirect: 'manual' }))
    assert.equal(page.status, 307)
    assert.match(page.headers.get('location') ?? '', /^\/login\?redirect=%2Fchat/)
    assert.equal(touchesCookie(page), false)
    const session = await rpcOutcome(await app.rpc('getSession', { method: 'GET', headers: dead }))
    assert.equal(session.result, null)
  })
})
