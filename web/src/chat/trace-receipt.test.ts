import assert from 'node:assert/strict'
import { test } from 'node:test'
import { es } from '../i18n/es.ts'
import { pt } from '../i18n/pt.ts'
import { translator } from '../i18n/translate.ts'
import { traceReceiptFacts } from './trace-receipt.ts'
import type { TraceReceipt } from './types.ts'

const receipt: TraceReceipt = {
  transaction_id: 'TXN-FIX0006', transaction_type: 'Transfer', transaction_date: '2024-01-10', amount: 150.5, currency: 'MXN',
  movement_status: 'Pending', trace_id: 'TR-15B5F466D9D65B60', trace_status: 'open', read_back: true, sla_business_days: null,
}

test('without a source-backed deadline the next step says there is none, in Spanish and Portuguese, and never promises 0 days', () => {
  const spanish = traceReceiptFacts(receipt, 'es', translator(es)).nextStep
  const portuguese = traceReceiptFacts(receipt, 'pt', translator(pt)).nextStep
  assert.equal(spanish, 'Próximo paso: Operaciones revisará el pedido. No hay un plazo de respuesta respaldado por una regla vigente para informarte.')
  assert.equal(portuguese, 'Próximo passo: Operações vai analisar o pedido. Não há um prazo de resposta respaldado por uma regra vigente para informar.')
  for (const text of [spanish, portuguese]) assert.doesNotMatch(text, /\b0\b|\{n\}/)
})

test('a deadline from a rule is said with its number, zero included', () => {
  assert.equal(traceReceiptFacts({ ...receipt, sla_business_days: 3 }, 'es', translator(es)).nextStep,
    'Próximo paso: Operaciones responderá en hasta 3 días hábiles.')
  assert.equal(traceReceiptFacts({ ...receipt, sla_business_days: 1 }, 'pt', translator(pt)).nextStep,
    'Próximo passo: Operações responderá em até 1 dia útil.')
  assert.match(traceReceiptFacts({ ...receipt, sla_business_days: 0 }, 'es', translator(es)).nextStep, /hasta 0 días hábiles/)
})
