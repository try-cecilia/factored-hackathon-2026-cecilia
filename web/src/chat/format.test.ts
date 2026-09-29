import assert from 'node:assert/strict'
import { test } from 'node:test'
import { optionAnswer, parseOptions, toBlocks } from './format.ts'

test('a product clarification becomes options answered by product name', () => {
  const parsed = parseOptions('¿Sobre cuál de tus productos? 1) Cuenta Ahorro ···0001 (USD); 2) Cuenta Ahorro ···0002 (USD)')
  assert.ok(parsed)
  assert.equal(parsed.lead, '¿Sobre cuál de tus productos?')
  assert.deepEqual(parsed.options, ['Cuenta Ahorro ···0001 (USD)', 'Cuenta Ahorro ···0002 (USD)'])
  assert.equal(parsed.tail, '')
  assert.equal(parsed.kind, 'product')
  assert.equal(optionAnswer(parsed, 1), 'Cuenta Ahorro ···0002')
})

test('a choice between pending movements keeps its closing question and is answered by number', () => {
  const parsed = parseOptions(
    'Tienes varios movimientos pendientes: 1) transferencia de 40.00 USD del 15/01/2024 (Cuenta Ahorro ···0010); ' +
      '2) operación de pago de 5.00 USD del 14/01/2024 (Cuenta Ahorro ···0010). ¿Cuál quieres rastrear? Responde con su número.',
  )
  assert.ok(parsed)
  assert.equal(parsed.kind, 'movement')
  assert.equal(parsed.options.length, 2)
  assert.equal(parsed.options[1], 'operación de pago de 5.00 USD del 14/01/2024 (Cuenta Ahorro ···0010)')
  assert.equal(parsed.tail, '¿Cuál quieres rastrear? Responde con su número.')
  assert.equal(optionAnswer(parsed, 1), '2')
})

test('the Portuguese version parses the same way', () => {
  const parsed = parseOptions('Você tem várias movimentações pendentes: 1) a (X ···1); 2) b (Y ···2). Qual quer rastrear? Responda com o número.')
  assert.ok(parsed)
  assert.equal(parsed.kind, 'movement')
  assert.equal(parsed.tail, 'Qual quer rastrear? Responda com o número.')
})

test('text without a numbered list, or with a single item, is shown as written', () => {
  assert.equal(parseOptions('¿Me cuentas un poco más qué necesitas?'), null)
  assert.equal(parseOptions('Elige: 1) una sola opción'), null)
})

test('dash lines become one list and the rest stays as paragraphs', () => {
  assert.deepEqual(toBlocks('- a\n- b\nInformación al 16/01/2024.'), [
    { type: 'ul', items: ['a', 'b'] },
    { type: 'p', text: 'Información al 16/01/2024.' },
  ])
})
