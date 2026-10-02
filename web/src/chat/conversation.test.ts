import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  caseCategoryKey, casesOf, caseTone, chosenOption, classifyReply, deliveryDetailKey, deliveryOf, fromHistory, isNo, isOpenCase, isYes,
  mergeCases, proposalState, sessionNotice, shortCaseId, splitCaseNews, type Entry,
} from './conversation.ts'
import { parseOptions } from './format.ts'
import type { Reply } from './types.ts'

const reply = (over: Partial<Reply> = {}): Reply => ({
  trace_id: 'abc12345', disposition: 'AUTO_RESOLVE', response_text: 'Tu saldo es 10.', language: 'es', category: 'resolved', ticket_id: null, latency_ms: 1, ...over,
})
const user = (text: string, over: Partial<Extract<Entry, { role: 'user' }>> = {}): Entry => ({ id: 1, role: 'user', text, at: 1, key: 'k', delivery: 'sent', ...over })
const assistant = (r: Reply): Entry => ({ id: 2, role: 'assistant', reply: r, at: 2 })
const proposal = reply({ disposition: 'CLARIFY', category: 'confirm_action', response_text: 'Encontré este movimiento. ¿Quieres que abra un pedido de rastreo? Responde sí o no.' })

test('the history becomes entries in order, the customer side already sent, closed by a resumed note', () => {
  const entries = fromHistory([{ role: 'user', text: 'hola', at: 10 }, { role: 'assistant', reply: reply(), at: 20 }], 5, 99)
  assert.deepEqual(entries.map((e) => [e.id, e.role]), [[5, 'user'], [6, 'assistant'], [7, 'note']])
  assert.equal((entries[0] as Extract<Entry, { role: 'user' }>).delivery, 'sent')
  assert.equal((entries[0] as Extract<Entry, { role: 'user' }>).key, null)
  assert.deepEqual(fromHistory([], 1, 1), [])
})

test('a lost answer is uncertain and safe to retry; a refusal never ran; a 409 is already processed', () => {
  assert.equal(deliveryOf('timeout'), 'uncertain')
  assert.equal(deliveryOf('unavailable'), 'uncertain')
  assert.equal(deliveryOf('unexpected'), 'uncertain')
  assert.equal(deliveryOf('rate_limited'), 'failed')
  assert.equal(deliveryOf('busy'), 'failed')
  assert.equal(deliveryOf('already_processed'), 'processed')
  assert.equal(deliveryDetailKey('unavailable'), 'uncertain')
  assert.equal(deliveryDetailKey('timeout'), 'timeout')
  assert.equal(deliveryDetailKey('rate_limited'), 'rateLimited')
  assert.equal(deliveryDetailKey('already_processed'), 'processed')
})

test('plain yes and no in both languages', () => {
  for (const yes of ['Sí', 'si', 'Sim', ' sim. ']) assert.ok(isYes(yes), yes)
  for (const no of ['No', 'Não', 'nao']) assert.ok(isNo(no), no)
  assert.ok(!isYes('sí, pero antes dime mi saldo') && !isNo('no sé'))
})

test('each disposition gets its component', () => {
  assert.deepEqual(classifyReply(reply()), { kind: 'answer' })
  assert.equal(classifyReply(reply({ disposition: 'ABSTAIN', category: 'out_of_scope' })).kind, 'decline')
  assert.deepEqual(classifyReply(reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: 'T-0123456789' })), { kind: 'handoff', ticketId: 'T-0123456789', category: 'theft' })
  assert.equal(classifyReply(proposal).kind, 'confirmTrace')
  const clarify = classifyReply(reply({ disposition: 'CLARIFY', category: 'missing_or_invalid_argument', response_text: '¿Sobre cuál? 1) Ahorro (MXN); 2) Corriente (MXN).' }))
  assert.equal(clarify.kind, 'clarify')
  assert.equal(clarify.kind === 'clarify' && clarify.options?.options.length, 2)
  const bare = classifyReply(reply({ disposition: 'CLARIFY', response_text: '¿Para qué fechas?' }))
  assert.deepEqual(bare, { kind: 'clarify', options: null })
})

test('a handoff with no case number is "could not verify", never a claim that a person has it', () => {
  assert.equal(classifyReply(reply({ disposition: 'ESCALATE', category: 'tool_failure', ticket_id: null })).kind, 'couldNotVerify')
})

test('the customer saying no to a trace gets an answer, not a refusal', () => {
  assert.equal(classifyReply(reply({ disposition: 'ABSTAIN', category: 'action_cancelled' })).kind, 'answer')
})

test('the answer that follows the customer\'s yes to a proposal is the action result; the same answer after a plain question is not', () => {
  const before: Entry[] = [assistant(proposal), user('Sí')]
  assert.equal(classifyReply(reply({ response_text: 'Listo: abrí el pedido de rastreo TR-1.' }), before).kind, 'actionResult')
  assert.equal(classifyReply(reply(), [user('¿Cuál es mi saldo?')]).kind, 'answer')
  assert.equal(classifyReply(reply(), [assistant(proposal), user('No')]).kind, 'answer')
})

test('a proposal is waiting until the customer answers, then it is sent, in flight, or declined', () => {
  assert.equal(proposalState([assistant(proposal)], 0, false), 'idle')
  assert.equal(proposalState([assistant(proposal), user('Sí', { delivery: 'sending' })], 0, true), 'loading')
  assert.equal(proposalState([assistant(proposal), user('Sí')], 0, false), 'sent')
  assert.equal(proposalState([assistant(proposal), user('No')], 0, false), 'declined')
  assert.equal(proposalState([assistant(proposal), user('otra cosa')], 0, false), 'declined')
  assert.equal(proposalState([assistant(proposal), user('Sí', { delivery: 'uncertain' })], 0, false), 'idle')
})

test('the option the customer picked is the one whose answer they sent next', () => {
  const options = parseOptions('¿Sobre cuál de tus productos? 1) Cuenta Ahorro (MXN); 2) Tarjeta (MXN)')
  assert.ok(options)
  const answer = (i: number) => options.options[i].replace(/\s*\([A-Z]{3}\)\s*$/, '')
  assert.equal(chosenOption(options, answer, user('Tarjeta')), 1)
  assert.equal(chosenOption(options, answer, user('otra')), undefined)
  assert.equal(chosenOption(options, answer, undefined), undefined)
})

test('what a person did with a case comes out of the reply as notes', () => {
  const text = 'Novedad de tu caso: un agente ya lo tomó y lo está revisando.\nNovidade do seu caso: x.\n\nTu saldo es 10.'
  assert.deepEqual(splitCaseNews(text), { news: ['Novedad de tu caso: un agente ya lo tomó y lo está revisando.', 'Novidade do seu caso: x.'], body: 'Tu saldo es 10.' })
  assert.deepEqual(splitCaseNews('Tu saldo es 10.\n- a\n- b'), { news: [], body: 'Tu saldo es 10.\n- a\n- b' })
  assert.deepEqual(splitCaseNews('Novedad de tu caso: solo eso.'), { news: ['Novedad de tu caso: solo eso.'], body: '' })
})

test('the cases are the handoffs that came with a number, newest first, once each', () => {
  const entries: Entry[] = [
    assistant(reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: 'T-0000000001' })),
    assistant(reply()),
    assistant(reply({ disposition: 'ESCALATE', category: 'tool_failure', ticket_id: null })),
    assistant(reply({ disposition: 'ESCALATE', category: 'trace_review', ticket_id: 'T-0000000002' })),
    assistant(reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: 'T-0000000001' })),
  ]
  assert.deepEqual(casesOf(entries).map((c) => c.ticketId), ['T-0000000001', 'T-0000000002'])
})

test('case status: open ones can still change, tones follow the meaning, unknown categories get a generic name', () => {
  assert.ok(isOpenCase('open') && isOpenCase('claimed') && !isOpenCase('approved') && !isOpenCase('stale') && !isOpenCase('resolved'))
  assert.deepEqual(
    ['open', 'claimed', 'approved', 'rejected', 'stale', 'handed_back', 'resolved', 'x'].map(caseTone),
    ['accent', 'accent', 'success', 'danger', 'caution', 'accent', 'success', 'accent'],
  )
  assert.equal(caseCategoryKey('theft'), 'theft')
  assert.equal(caseCategoryKey('turn_timeout'), 'pending')
  assert.equal(caseCategoryKey('something_new'), 'other')
})

test('a case number is shortened in lists only when it is a long id', () => {
  assert.equal(shortCaseId('55d09c14-2235-4c3c-8967-ccac61db9c50'), '55d09c14')
  assert.equal(shortCaseId('T-0123456789'), 'T-0123456789')
})

test('a message whose answer the API dropped is "received" with its own honest text, and cases merge newest first, once each', () => {
  assert.equal(deliveryOf('answer_gone'), 'processed')
  assert.equal(deliveryDetailKey('answer_gone'), 'processedGone')
  const merged = mergeCases([{ ticketId: 'A', category: 'theft', at: 1 }, { ticketId: 'B', category: 'fraud', at: 3 }], [{ ticketId: 'A', category: 'theft', at: 9 }, { ticketId: 'C', category: 'x', at: 2 }])
  assert.deepEqual(merged.map((c) => c.ticketId), ['B', 'C', 'A'])
})

test('the session countdown shows nothing until two minutes are left, then the minutes, then that it is over', () => {
  assert.equal(sessionNotice(900), null)
  assert.equal(sessionNotice(121), null)
  assert.equal(sessionNotice(120), 2)
  assert.equal(sessionNotice(61), 2)
  assert.equal(sessionNotice(60), 1)
  assert.equal(sessionNotice(1), 1)
  assert.equal(sessionNotice(0), 0)
  assert.equal(sessionNotice(-5), 0)
})

test('the options of a clarification are what the API says they are, whatever the answered part before them mentions', () => {
  const text = 'Movimientos pendientes:\n- 16/01/2024: transferencia 640.00 USD (pendiente)\n\n¿Sobre cuál de tus productos? 1) Cuenta Ahorro ···0001 (USD); 2) Cuenta Ahorro ···0002 (USD)'
  const product = classifyReply(reply({ disposition: 'CLARIFY', category: 'missing_or_invalid_argument', response_text: text, choice: 'product' }))
  assert.equal(product.kind, 'clarify')
  assert.equal(product.kind === 'clarify' && product.options?.kind, 'product')
  const movement = classifyReply(reply({ disposition: 'CLARIFY', category: 'missing_or_invalid_argument', choice: 'movement',
    response_text: 'Tienes varios movimientos pendientes: 1) a (X ···1); 2) b (Y ···2). ¿Cuál quieres rastrear? Responde con su número.' }))
  assert.equal(movement.kind === 'clarify' && movement.options?.kind, 'movement')
})
