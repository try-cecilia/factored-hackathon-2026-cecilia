import assert from 'node:assert/strict'
import { test } from 'node:test'
import { es } from '../i18n/es.ts'
import { pt } from '../i18n/pt.ts'
import { translator } from '../i18n/translate.ts'
import type { Locale } from '../i18n/locales.ts'
import type { CaseRow } from './ConversationProvider.tsx'
import type { AssistantEntry, Entry, FailureKind, UserEntry } from './conversation.ts'
import { conversationTranscript, hasMessages } from './transcript.ts'
import type { Disposition } from './types.ts'

const AT = Date.UTC(2026, 9, 1, 15, 38)
const options = (locale: Locale, cases: CaseRow[] = []) => ({ locale, t: translator(locale === 'es' ? es : pt), cases, timeZone: 'UTC' })

let id = 0
const user = (text: string, at = AT): UserEntry => ({ id: ++id, role: 'user', text, at, key: null, delivery: 'sent' })
const reply = (text: string, extra: Partial<AssistantEntry['reply']> = {}, at = AT): AssistantEntry => ({
  id: ++id,
  role: 'assistant',
  at,
  reply: { trace_id: 'trace-9f8e7d6c', disposition: 'AUTO_RESOLVE' as Disposition, response_text: text, language: 'es', category: 'balance', ticket_id: null, latency_ms: 12, ...extra },
})

test('a conversation is the date, then one line per message with its hour and who said it', () => {
  const entries: Entry[] = [user('¿Cuál es mi saldo?'), reply('Tu saldo es 10.00 USD.', {}, AT + 60_000)]
  assert.equal(
    conversationTranscript(entries, options('es')),
    ['Conversación con Cecilia · 01/10/2026', '[15:38] Tú: ¿Cuál es mi saldo?', '[15:39] Cecilia: Tu saldo es 10.00 USD.'].join('\n'),
  )
})

test('in Portuguese the title and the names are Portuguese', () => {
  const entries: Entry[] = [user('Qual é o meu saldo?'), reply('Seu saldo é 10,00 USD.', { language: 'pt' })]
  assert.equal(
    conversationTranscript(entries, options('pt')),
    ['Conversa com a Cecilia · 01/10/2026', '[15:38] Você: Qual é o meu saldo?', '[15:38] Cecilia: Seu saldo é 10,00 USD.'].join('\n'),
  )
})

test('paragraphs stay lines and dash lists stay dash lists, with the amounts and masked numbers as the reply wrote them', () => {
  const text = 'Estos son tus últimos movimientos:\n- 15/01/2024 · Transferencia · −40.00 USD (Cuenta Ahorro ···0010)\n• 14/01/2024 · Pago · −5.00 USD\n\n¿Algo más?'
  const out = conversationTranscript([user('Mis últimos movimientos'), reply(text)], options('es')).split('\n')
  assert.deepEqual(out.slice(2), [
    '[15:38] Cecilia: Estos son tus últimos movimientos:',
    '- 15/01/2024 · Transferencia · −40.00 USD (Cuenta Ahorro ···0010)',
    '- 14/01/2024 · Pago · −5.00 USD',
    '¿Algo más?',
  ])
})

test('a reply that opens with a list has its heading on a line of its own', () => {
  const out = conversationTranscript([user('Mi saldo'), reply('- Cuenta Ahorro ···0001: saldo 10.00 USD\n- Cuenta Corriente ···0003: saldo 5.00 USD\nInformación al 16/01/2024.')], options('es')).split('\n')
  assert.deepEqual(out.slice(2), ['[15:38] Cecilia:', '- Cuenta Ahorro ···0001: saldo 10.00 USD', '- Cuenta Corriente ···0003: saldo 5.00 USD', 'Información al 16/01/2024.'])
})

test('a question with options reads as the question, its options and what it asks at the end', () => {
  const text = 'Tienes varios movimientos pendientes: 1) transferencia de 40.00 USD del 15/01/2024 (Cuenta Ahorro ···0010); 2) pago de 5.00 USD del 14/01/2024 (Cuenta Ahorro ···0010). ¿Cuál quieres rastrear?'
  const out = conversationTranscript([user('Hice un pago y no llega'), reply(text, { disposition: 'CLARIFY', category: 'clarify' })], options('es')).split('\n')
  assert.deepEqual(out.slice(2), [
    '[15:38] Cecilia: Tienes varios movimientos pendientes:',
    '- transferencia de 40.00 USD del 15/01/2024 (Cuenta Ahorro ···0010)',
    '- pago de 5.00 USD del 14/01/2024 (Cuenta Ahorro ···0010)',
    '¿Cuál quieres rastrear?',
  ])
})

test('a proposal to trace says how it ended, and the opened trace carries its title', () => {
  const proposal = reply('Encontré el pago pendiente. ¿Quieres que abra un rastreo?', { disposition: 'CLARIFY', category: 'confirm_action' })
  const done = reply('Listo: abrí el rastreo TR-1.')
  const pending: Entry[] = [user('Mi pago no llega'), proposal]
  assert.ok(!conversationTranscript(pending, options('es')).includes('Solicitud enviada'))

  const out = conversationTranscript([...pending, user('Sí'), done], options('es')).split('\n')
  assert.deepEqual(out.slice(2), [
    '[15:38] Cecilia: Encontré el pago pendiente. ¿Quieres que abra un rastreo?',
    'Solicitud enviada',
    '[15:38] Tú: Sí',
    '[15:38] Cecilia: Rastreo abierto',
    'Listo: abrí el rastreo TR-1.',
  ])

  const declined = conversationTranscript([...pending, user('No')], options('es'))
  assert.ok(declined.endsWith('Sin rastrear por ahora\n[15:38] Tú: No'))
})

test('a handoff reads its case card: what it is about, where it stands and its number', () => {
  const handoff = reply('Pasé tu consulta a una persona del equipo.', { disposition: 'ESCALATE', category: 'fraud', ticket_id: 'CASE-0042' })
  const ready: CaseRow = { ref: { ticketId: 'CASE-0042', category: 'fraud', at: AT }, state: { state: 'ready', status: 'claimed', message: null } }
  const asked = (cases: CaseRow[]) => conversationTranscript([user('No reconozco un cargo'), handoff], options('es', cases)).split('\n').slice(2)

  assert.deepEqual(asked([ready]), ['[15:38] Cecilia: Pasé tu consulta a una persona del equipo.', 'Posible fraude · En revisión · #CASE-0042'])
  assert.equal(asked([])[1], 'Posible fraude · Consultando el estado… · #CASE-0042')
})

test('what a person did with a case, shown as a note over the reply, is part of the reply', () => {
  const text = 'Novedad de tu caso: aprobamos el rastreo.\n\nTu saldo es 10.00 USD.'
  const out = conversationTranscript([user('Hola'), reply(text)], options('es')).split('\n')
  assert.deepEqual(out.slice(2), ['[15:38] Cecilia: Novedad de tu caso: aprobamos el rastreo.', 'Tu saldo es 10.00 USD.'])
})

test('nothing internal to a reply is copied, and the "conversation resumed" note is not a message', () => {
  const secret = reply('Tu saldo es 10.00 USD.', {
    category: 'internal_category_x',
    why: { rule: 'rule_secret', because: { en: 'because_secret', es: 'porque_secreto' }, model: { called: true, provider: 'p', model: 'm', saw: 'saw_secret', chose: [] }, checks: [], llm_calls: 1, cost_usd: 0.1, latency_ms: 9 },
  })
  const note: Entry = { id: ++id, role: 'note', note: 'restored', at: AT }
  const out = conversationTranscript([user('Saldo'), secret, note], options('es'))
  for (const hidden of ['trace-9f8e7d6c', 'AUTO_RESOLVE', 'internal_category_x', 'rule_secret', 'because_secret', 'porque_secreto', 'saw_secret', 'Conversación retomada']) {
    assert.ok(!out.includes(hidden), hidden)
  }
  assert.equal(out.split('\n').length, 3)
})

test('what the customer typed goes as typed, line breaks included', () => {
  const out = conversationTranscript([user('Hola\n- uno\n- dos')], options('es')).split('\n')
  assert.deepEqual(out.slice(1), ['[15:38] Tú: Hola', '- uno', '- dos'])
})

test('an empty conversation has nothing to copy', () => {
  const note: Entry = { id: ++id, role: 'note', note: 'restored', at: AT }
  assert.equal(conversationTranscript([], options('es')), '')
  assert.equal(conversationTranscript([note], options('es')), '')
  assert.equal(hasMessages([]), false)
  assert.equal(hasMessages([note]), false)
  assert.equal(hasMessages([user('Hola')]), true)
})

const unsent = (text: string, delivery: UserEntry['delivery'], failure?: FailureKind): UserEntry => ({ ...user(text), delivery, failure })

test('a message that did not go says so, with the reason the screen gives', () => {
  const rows = (locale: Locale, entry: UserEntry) => conversationTranscript([entry], options(locale)).split('\n').slice(1)
  assert.deepEqual(rows('es', unsent('Mi saldo', 'failed', 'rate_limited')), [
    '[15:38] Tú: Mi saldo',
    'No se envió',
    'Se están enviando mensajes muy rápido. Esperar un minuto e intentar de nuevo.',
  ])
  assert.deepEqual(rows('pt', unsent('Meu saldo', 'failed', 'rate_limited')), [
    '[15:38] Você: Meu saldo',
    'Não enviado',
    'Você está enviando mensagens muito rápido. Espere um minuto e tente de novo.',
  ])
})

test('a lost answer, a message the API has and one still on its way each carry their own state', () => {
  const lines = (entry: UserEntry) => conversationTranscript([entry], options('es')).split('\n').slice(2)
  assert.deepEqual(lines(unsent('Hola', 'uncertain', 'timeout')), ['Sin confirmar', 'Tardó demasiado en responder y no pude confirmar si tu mensaje llegó. Reintentar es seguro: si ya lo recibió, no se repite.'])
  assert.deepEqual(lines(unsent('Hola', 'processed', 'answer_gone')), ['Recibido', 'El servicio recibió este mensaje, pero su respuesta ya no está guardada y no se puede mostrar. Preguntar de nuevo.'])
  assert.deepEqual(lines(unsent('Hola', 'sending')), ['Enviando'])
  assert.deepEqual(lines(user('Hola')), [])
})

test('a reply made in limited mode carries the notice, after the case news and before its text', () => {
  const degraded = reply('Novedad de tu caso: aprobamos el rastreo.\n\nTu saldo es 10.00 USD.', { degraded: true })
  const es = conversationTranscript([user('Saldo'), degraded], options('es')).split('\n').slice(2)
  assert.deepEqual(es, [
    '[15:38] Cecilia: Novedad de tu caso: aprobamos el rastreo.',
    'Cecilia está limitada por ahora: solo puede consultar saldos simples y lo demás lo revisa una persona.',
    'Tu saldo es 10.00 USD.',
  ])
  const pt = conversationTranscript([user('Saldo'), reply('Seu saldo é 10,00 USD.', { degraded: true })], options('pt')).split('\n').slice(2)
  assert.equal(pt[0], '[15:38] Cecilia: A Cecilia está limitada por enquanto: só consegue consultar saldos simples e o resto é analisado por uma pessoa.')
  assert.equal(pt[1], 'Seu saldo é 10,00 USD.')
})
