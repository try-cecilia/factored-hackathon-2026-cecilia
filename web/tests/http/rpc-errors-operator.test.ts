// F7, console side (the customer side is rpc-errors.test.ts): an API answer that breaks the contract is a status the console can
// explain, never a parser's message; a failure of the console's own handler is a generic error; a validator's message stays.
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ADMIN, ANA, SAME_ORIGIN, sessionCookie, startConsole } from './harness.ts'
import { rpcOutcome } from './rpc.ts'

const CANARY = 'CANARY-internal-body-9f3a'
const LEAKS = new RegExp(`${CANARY}|Unexpected token|not valid JSON|JSON|Cannot read properties|SyntaxError|TypeError`, 'i')

let app: Awaited<ReturnType<typeof startConsole>>
let operator: string
before(async () => {
  app = await startConsole()
  operator = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: SAME_ORIGIN }))!
})
after(() => app.close())

describe('an unexpected failure of a console read reaches the browser as a plain answer or a generic error', () => {
  test('ticket read: the API answers 200 with a body that is not JSON', async () => {
    app.answerRaw('/admin/tickets/', 200, `<<${CANARY}>>`)
    try {
      const answer = await rpcOutcome(await app.rpc('loadTicket', { method: 'GET', data: { ticket_id: 'TKT-0001-ABCD' }, headers: { Cookie: operator } }))
      assert.doesNotMatch(answer.text, LEAKS)
      assert.deepEqual(answer.result, { ok: false, status: 502 })
    } finally { app.answerNormally() }
  })

  test('a 5xx with valid JSON that carries a detail keeps its status and loses the detail', async () => {
    for (const status of [500, 502, 503]) {
      app.answerRaw('/admin/tickets/', status, JSON.stringify({ detail: `${CANARY} at /srv/api/desk.py line 12` }))
      try {
        const answer = await rpcOutcome(await app.rpc('loadTicket', { method: 'GET', data: { ticket_id: 'TKT-0001-ABCD' }, headers: { Cookie: operator } }))
        assert.doesNotMatch(answer.text, /CANARY|desk\.py/)
        assert.deepEqual(answer.result, { ok: false, status })
      } finally { app.answerNormally() }
    }
  })

  test('the details the console needs stay public: a 400 and a 409 on a decision keep the API\'s message', async () => {
    const operatorKeys = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN, operator_key: ANA }, headers: SAME_ORIGIN }))!
    for (const [status, detail] of [[400, 'a reason is required'], [409, 'the ticket changed: version 3']] as const) {
      app.answerRaw('/admin/tickets/', status, JSON.stringify({ detail }))
      try {
        const answer = await rpcOutcome(await app.rpc('actOnTicket', { data: { ticket_id: 'TKT-0001-ABCD', action: 'claim' }, headers: { Cookie: operatorKeys } }))
        assert.deepEqual(answer.result, { ok: false, status, message: detail })
      } finally { app.answerNormally() }
    }
  })

  test('queue read: the queue is JSON but not a list, so the console\'s own mapping throws', async () => {
    app.answerRaw('/admin/human_queue', 200, 'null')
    try {
      const answer = await rpcOutcome(await app.rpc('loadQueue', { method: 'GET', data: false, headers: { Cookie: operator } }))
      assert.doesNotMatch(answer.text, LEAKS)
      assert.equal(answer.error, 'internal error')
    } finally { app.answerNormally() }
  })

  test('a deliberate public error keeps its message', async () => {
    const answer = await rpcOutcome(await app.rpc('loadTicket', { method: 'GET', data: { ticket_id: '!' }, headers: { Cookie: operator } }))
    assert.equal(answer.error, 'ticket_id is not valid')
  })
})
