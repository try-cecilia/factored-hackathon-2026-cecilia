import assert from 'node:assert/strict'
import { test } from 'node:test'
import { es } from '../../i18n/es.ts'
import { pt } from '../../i18n/pt.ts'
import { translator } from '../../i18n/translate.ts'
import { attemptOutcomeName, attemptReasonName, errorTypeName, evidenceTypeName, keyName, nextStepText, questionTexts, reasonText, reviewReasonName, ruleName, type Texts } from './notes.ts'

const spanish = translator(es)
const portuguese = translator(pt)

const base: Texts = {
  reason: 'The customer confirmed a trace, but the movement needs a person\'s approval (older_than_review_threshold).',
  open_questions: ['Approve or reject the trace: older_than_review_threshold.', 'Evidence was not gathered: the handoff\'s time budget was spent.'],
  suggested_next_step: 'Review the movement (see pending_action.review_reason) and approve or reject the trace the customer asked for.',
}
const withCodes: Texts = {
  ...base,
  reason_code: { code: 'trace_review', params: { review_reason: 'older_than_review_threshold' } },
  open_question_codes: [{ code: 'decide_trace', params: { review_reason: 'older_than_review_threshold' } }, { code: 'evidence_skipped_budget', params: {} }],
  next_step_code: 'trace_review',
}

test('a case with codes is written in the language of the operator, with the parameters translated too', () => {
  assert.equal(reasonText(spanish, withCodes), 'El cliente confirmó un rastreo, pero el movimiento necesita la aprobación de una persona (Pendiente desde hace más tiempo del que admite un rastreo simple).')
  assert.equal(reasonText(portuguese, withCodes), 'O cliente confirmou um rastreio, mas a movimentação precisa da aprovação de uma pessoa (Pendente há mais tempo do que um rastreio simples admite).')
  assert.deepEqual(questionTexts(spanish, withCodes), ['Aprobar o rechazar el rastreo: Pendiente desde hace más tiempo del que admite un rastreo simple.', 'No se reunió evidencia: se agotó el tiempo del traspaso.'])
  assert.match(nextStepText(portuguese, withCodes), /^Revisar a movimentação/)
})

test('a case without codes shows the English text as it came', () => {
  assert.equal(reasonText(spanish, base), base.reason)
  assert.deepEqual(questionTexts(portuguese, base), base.open_questions)
  assert.equal(nextStepText(spanish, base), base.suggested_next_step)
})

test('a code the console does not know, a malformed one, or one whose data is missing falls back to the English text', () => {
  const odd = {
    ...base,
    reason_code: { code: 'a_reason_from_the_future', params: {} },
    open_question_codes: [{ code: 'decide_trace' }, null] as never, // decide_trace needs review_reason: without it the text would say {review_reason}
    next_step_code: '../operator',
  }
  assert.equal(reasonText(spanish, odd), base.reason)
  assert.deepEqual(questionTexts(spanish, odd), base.open_questions)
  assert.equal(nextStepText(spanish, odd), base.suggested_next_step)
  assert.equal(nextStepText(spanish, { ...base, next_step_code: 'ticket' }), base.suggested_next_step) // a branch of the dictionary is not a text
})

test('an old case and a new one mix: each question uses the code at its own position, and the ones without keep their text', () => {
  const partial = { ...base, open_question_codes: [null, { code: 'evidence_skipped_budget', params: {} }] }
  assert.deepEqual(questionTexts(spanish, partial), [base.open_questions[0], 'No se reunió evidencia: se agotó el tiempo del traspaso.'])
})

test('the categories of a safety reason are translated one by one', () => {
  const text = reasonText(spanish, { ...base, reason: 'Safety signal in the request: fraud, theft.', reason_code: { code: 'safety_signal', params: { categories: 'fraud, theft' } } })
  assert.equal(text, 'Señal de seguridad en el pedido: Fraude, Robo.')
})

test('policy rules: whole, by family, with a mark, and unknown ones as they came', () => {
  assert.equal(ruleName(spanish, 'action:trace_review'), 'Rastreo: lo decide una persona')
  assert.equal(ruleName(portuguese, 'customer_status == Suspended'), 'Cliente com a conta suspensa')
  assert.equal(ruleName(spanish, 'lexicon:fraud'), 'Léxico de seguridad: Fraude')
  assert.equal(ruleName(spanish, 'tool_error:DataUnavailable'), 'Error de herramienta: DataUnavailable')
  assert.equal(ruleName(spanish, 'action:trace_unverified|handoff_unverified'), 'Rastreo: el servicio no lo confirmó · traspaso sin confirmar')
  assert.equal(ruleName(spanish, 'a_rule_from_the_future'), 'a_rule_from_the_future')
  assert.equal(ruleName(spanish, 'lexicon'), 'lexicon')
  assert.equal(ruleName(spanish, ''), '—')
})

test('evidence types, fact keys, review reasons, attempts and error types: known ones translated, the rest as they came', () => {
  assert.equal(evidenceTypeName(spanish, 'denied_request'), 'Pedido denegado')
  assert.equal(evidenceTypeName(portuguese, 'transaction'), 'Movimentação')
  assert.equal(evidenceTypeName(spanish, 'something_new'), 'something_new')
  assert.equal(keyName(portuguese, 'tool'), 'Ferramenta')
  assert.equal(keyName(spanish, 'weird key.with dots'), 'weird key.with dots')
  assert.equal(reviewReasonName(spanish, 'before_product_opening'), 'La fecha es anterior a la apertura del producto')
  assert.equal(reviewReasonName(spanish, 'a_new_review'), 'a_new_review')
  assert.equal(attemptOutcomeName(portuguese, 'skipped'), 'ignorado')
  assert.equal(attemptReasonName(spanish, 'circuit_open'), 'proveedor en pausa tras fallas repetidas')
  assert.equal(attemptReasonName(spanish, 'GROQ_API_KEY not set'), 'falta la clave GROQ_API_KEY')
  assert.equal(attemptReasonName(spanish, 'a reason from the future'), 'a reason from the future')
  assert.equal(errorTypeName(spanish, 'PermissionDenied'), 'Recurso de otro cliente')
  assert.equal(errorTypeName(spanish, 'ZeroDivisionError'), 'ZeroDivisionError')
})

test('a parameter that is null, empty or not a text or a number falls back to the English text, in both languages; zero is a value', () => {
  const review = (review_reason: unknown) => ({ ...base, reason_code: { code: 'trace_review', params: { review_reason } }, open_question_codes: [{ code: 'decide_trace', params: { review_reason } }, null] }) as unknown as Texts
  for (const bad of [null, '', '   ', undefined, {}, [], NaN]) {
    for (const t of [spanish, portuguese]) {
      assert.equal(reasonText(t, review(bad)), base.reason, String(bad))
      assert.deepEqual(questionTexts(t, review(bad)), base.open_questions, String(bad))
    }
  }
  const count = { ...base, reason: 'The request names 0 product(s) owned by another customer.', reason_code: { code: 'foreign_reference', params: { count: 0 } } }
  assert.equal(reasonText(spanish, count), 'El pedido nombra 0 producto(s) de otro cliente.')
})
