import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { startCustomerApp, TOKEN } from './customer-harness.ts'

const turns = [
  { role: 'user', text: 'Me clonaron la tarjeta', at: 1_760_000_000 },
  {
    role: 'assistant', text: 'Voy a transferir tu caso a un agente especializado.', at: 1_760_000_001, trace_id: 'abc12345', disposition: 'ESCALATE',
    category: 'theft', language: 'es', ticket_id: '55d09c14-2235-4c3c-8967-ccac61db9c50', degraded: false,
  },
]
const scenarios = [
  { id: 'a', path: 'normal', customer_id: 'CLI-FIX0001', language: 'es', fault: null, turns: ['hola'], expect: [null], title: { en: 'Balance', es: 'Consulta de saldo' }, look_for: { en: 'x', es: 'y' }, test_pin: '123456' },
]

let history: unknown = { turns, cases: [{ ticket_id: '55d09c14-2235-4c3c-8967-ccac61db9c50', category: 'theft', at: 1_760_000_001 }] }
const goodHistory = history
let historyStatus = 200
let demo = false
let demoDelay = 0
let app: Awaited<ReturnType<typeof startCustomerApp>>
// The drawn panel: its texts also travel in the page's dictionary (the root loader's data), so the text alone proves nothing.
const demoPanel = /<aside class="demo" aria-labelledby="demo-title">/

before(async () => {
  app = await startCustomerApp((req, reply) => {
    if (req.url === '/chat/history') return reply(historyStatus, historyStatus === 200 ? history : { detail: 'invalid or expired session' })
    if (req.url === '/demo/scenarios') {
      if (!demo) return reply(404, { detail: 'Not Found' })
      setTimeout(() => reply(200, scenarios), demoDelay)
      return true
    }
    if (req.url === '/demo/customers') return reply(404, { detail: 'Not Found' })
    if (req.url?.startsWith('/case/')) return reply(200, { ticket_id: 'x', status: 'claimed', message: null })
    return false
  })
})
after(() => app.close())

const cookie = { Cookie: `__Host-cecilai_session=${TOKEN}` }

describe('the customer chat page', () => {
  test('without a session it goes to sign in, and comes back to the chat', async () => {
    const res = await app.get('/chat')
    assert.equal(res.status, 307)
    assert.match(res.headers.get('location') ?? '', /^\/login\?redirect=%2Fchat/)
  })

  test('a reload shows the conversation the API kept, already rendered by the server', async () => {
    historyStatus = 200
    const res = await app.get('/chat', cookie)
    assert.equal(res.status, 200)
    const html = await res.text()
    assert.match(html, /Me clonaron la tarjeta/)
    assert.match(html, /Voy a transferir tu caso a un agente especializado\./)
    assert.match(html, /Conversación retomada/)
    assert.match(html, /<html[^>]*lang="es"/)
  })

  test('the case appears in the sidebar and the handoff message carries its number', async () => {
    const html = await (await app.get('/chat', cookie)).text()
    assert.match(html, /Robo o clonación de tarjeta/)
    assert.match(html, /55d09c14-2235-4c3c-8967-ccac61db9c50/)
  })

  test('in Portuguese the screen is in Portuguese and the assistant\'s own text is untouched', async () => {
    const html = await (await app.get('/chat', { ...cookie, 'Accept-Language': 'pt-BR,pt;q=0.9' })).text()
    assert.match(html, /<html[^>]*lang="pt-BR"/)
    assert.match(html, /Conversa retomada/)
    assert.match(html, /Roubo ou clonagem de cartão/)
    assert.match(html, /Voy a transferir tu caso a un agente especializado\./)
  })

  test('the page carries only the customer\'s texts, in its language, and every key on screen was found', async () => {
    const spanish = await (await app.get('/chat', cookie)).text()
    assert.match(spanish, /Nada se hace sin tu confirmación|Conversación retomada/)
    for (const other of ['Ingreso de operador · Cecilai', 'Solo lectura. Sale de los últimos turnos', 'Galería de componentes', 'Nada é feito sem a sua confirmação']) {
      assert.ok(!spanish.includes(other), other)
    }
    const portuguese = await (await app.get('/chat', { ...cookie, 'Accept-Language': 'pt-BR' })).text()
    assert.match(portuguese, /Nada é feito sem a sua confirmação/)
    assert.ok(!portuguese.includes('Conversación retomada'))
    // A key outside the loaded areas would be drawn as itself.
    for (const html of [spanish, portuguese]) assert.doesNotMatch(html, />\s*(common|shell|home|login|loaders|sidebar|chat|cases|conversation|demo)\.[a-z][\w.]*\s*</)
  })

  test('the session token stays on the server: the page never contains it, and the API got it only in the header', async () => {
    const html = await (await app.get('/chat', cookie)).text()
    assert.ok(!html.includes(TOKEN))
    const historyCalls = app.seen.filter((c) => c.url === '/chat/history')
    assert.ok(historyCalls.length > 0 && historyCalls.every((c) => c.token === TOKEN))
  })

  test('a conversation that cannot be read does not break the page', async () => {
    history = { not: 'a history' }
    const res = await app.get('/chat', cookie)
    assert.equal(res.status, 200)
    assert.match(await res.text(), /No pude recuperar la conversación anterior\./)
    history = goodHistory
  })

  test('a session the API says is over goes back to sign in', async () => {
    historyStatus = 401
    const res = await app.get('/chat', cookie)
    assert.equal(res.status, 307)
    assert.match(res.headers.get('location') ?? '', /^\/login\?redirect=%2Fchat/)
    historyStatus = 200
  })

  test('the demo panel exists only when the sandbox does, marked as Demo, and never shows a test PIN', async () => {
    demo = false
    assert.doesNotMatch(await (await app.get('/chat', cookie)).text(), demoPanel)
    demo = true
    const html = await (await app.get('/chat', cookie)).text()
    assert.match(html, demoPanel)
    assert.match(html, /Ayudas de demostración/)
    assert.match(html, /Consulta de saldo/)
    assert.ok(!html.includes('123456'))
    demo = false
  })

  test('a slow sandbox does not hold the chat: the conversation arrives first, the demo panel later in the same page', async () => {
    demo = true
    demoDelay = 1500
    const started = Date.now()
    const res = await app.get('/chat', cookie)
    assert.equal(res.status, 200)
    const reader = (res.body as ReadableStream<Uint8Array>).getReader()
    const decoder = new TextDecoder()
    let html = ''
    while (!html.includes('Me clonaron la tarjeta')) {
      const { done, value } = await reader.read()
      assert.ok(!done, 'the page ended without the conversation')
      html += decoder.decode(value, { stream: true })
    }
    assert.ok(Date.now() - started < 1000, `the conversation took ${Date.now() - started} ms`)
    assert.doesNotMatch(html, demoPanel)
    for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) html += decoder.decode(chunk.value, { stream: true })
    assert.match(html, demoPanel)
    assert.ok(!html.includes('123456'))
    demo = false
    demoDelay = 0
  })

  test('with DEMO_MODE=0 given to the web it never asks the API for the demo, and the chat is complete', async () => {
    demo = true
    process.env.DEMO_MODE = '0'
    const before = app.seen.filter((c) => c.url === '/demo/scenarios').length
    try {
      const html = await (await app.get('/chat', cookie)).text()
      assert.match(html, /Me clonaron la tarjeta/)
      assert.doesNotMatch(html, demoPanel)
      assert.equal(app.seen.filter((c) => c.url === '/demo/scenarios').length, before)
    } finally {
      delete process.env.DEMO_MODE
      demo = false
    }
  })
})
