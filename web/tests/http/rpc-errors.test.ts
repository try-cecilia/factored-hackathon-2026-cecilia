// F7 (customer side): what an unexpected failure inside a server function sends to the browser. The framework serializes a thrown Error's message,
// so a parser error that quotes the API's body, or a TypeError that names a field, would travel to the page. Deliberate public
// errors (a validator saying the input is wrong) keep their message.
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { startCustomerApp, TOKEN } from './customer-harness.ts'
import { rpcOutcome } from './rpc.ts'

const CANARY = 'CANARY-internal-body-9f3a'
const GENERIC = 'internal error'
// What must not reach the browser: the API's body, the parser's own words, a field of our code.
const LEAKS = new RegExp(`${CANARY}|Unexpected token|not valid JSON|JSON|Cannot read properties|customer_id|agent API|SyntaxError|TypeError`, 'i')

// One fake API per process: the built app reads AGENT_API_URL on every call, so the console's side is in rpc-errors-operator.test.ts.
let customer: Awaited<ReturnType<typeof startCustomerApp>>
before(async () => { customer = await startCustomerApp(() => false) })
after(() => customer.close())

const cookie = { Cookie: `cecilai_session=${TOKEN}` }
const sessionRead = (req: { url?: string; method?: string }) => req.url === '/auth/session' && req.method === 'GET'
const loginPost = (req: { url?: string; method?: string }) => req.url === '/auth/session' && req.method === 'POST'

describe('an unexpected failure reaches the browser as a generic error', () => {
  test('login: the API answers 200 with a body that is not JSON', async () => {
    customer.answerRaw(loginPost, 200, `<html>${CANARY}</html>`)
    try {
      const answer = await rpcOutcome(await customer.signIn())
      assert.doesNotMatch(answer.text, LEAKS)
      assert.notDeepEqual(answer.result, { ok: true })
    } finally { customer.answerNormally() }
  })

  test('session read: the API answers 200 with a body that is not JSON', async () => {
    customer.answerRaw(sessionRead, 200, `{"oops": ${CANARY}`)
    try {
      const answer = await rpcOutcome(await customer.rpc('getSession', { method: 'GET', headers: cookie }))
      assert.doesNotMatch(answer.text, LEAKS)
      assert.equal(answer.error, GENERIC)
    } finally { customer.answerNormally() }
  })

  test('session read: a handler that throws for its own reasons (the body is JSON but not a session)', async () => {
    customer.answerRaw(sessionRead, 200, 'null')
    try {
      const answer = await rpcOutcome(await customer.rpc('getSession', { method: 'GET', headers: cookie }))
      assert.doesNotMatch(answer.text, LEAKS)
      assert.equal(answer.error, GENERIC)
    } finally { customer.answerNormally() }
  })

  test('a deliberate public error keeps its message', async () => {
    assert.equal((await rpcOutcome(await customer.rpc('getCase', { method: 'GET', data: { ticket_id: 'x' }, headers: cookie }))).error, 'invalid ticket id')
    assert.equal((await rpcOutcome(await customer.rpc('login', { data: { customer_id: 'x', pin: '1' } }))).error, 'customer_id must be 3-32 characters')
  })
})
