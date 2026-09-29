import assert from 'node:assert/strict'
import { test } from 'node:test'
import { es } from './es.ts'
import { pt } from './pt.ts'
import { format, lookup, translate, translator } from './translate.ts'

function flatten(node: unknown, prefix = ''): Map<string, string> {
  const out = new Map<string, string>()
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out.set(path, value)
    else for (const [nested, text] of flatten(value, path)) out.set(nested, text)
  }
  return out
}

const spanish = flatten(es)
const portuguese = flatten(pt)
const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()

test('Spanish and Portuguese have exactly the same keys', () => {
  assert.deepEqual([...portuguese.keys()].sort(), [...spanish.keys()].sort())
})

test('no text is empty', () => {
  for (const [key, text] of [...spanish, ...portuguese]) assert.notEqual(text.trim(), '', key)
})

test('each key uses the same placeholders in both languages', () => {
  for (const [key, text] of spanish) assert.deepEqual(placeholders(portuguese.get(key) ?? ''), placeholders(text), key)
})

test('the Spanish is neutral: no voseo in the UI copy', () => {
  const voseo = /\b(probá|ingresá|volvé|elegí|escribí|hacé|mirá|tenés|podés|querés|sabés)\b/i
  for (const [key, text] of spanish) assert.doesNotMatch(text, voseo, key)
})

test('translate interpolates and reports a missing param instead of printing undefined', () => {
  assert.equal(translate('es', 'shell.customer', { id: 'C-0007' }), 'Cliente C-0007')
  assert.equal(translate('pt', 'shell.customer', { id: 'C-0007' }), 'Cliente C-0007')
  assert.equal(format('Hola {name} ({n})', { name: 'Ana', n: 2 }), 'Hola Ana (2)')
  assert.equal(format('Hola {name}', {}), 'Hola {name}')
})

test('translator binds a language and lookup ignores keys that are not strings', () => {
  const t = translator('pt')
  assert.equal(t('shell.signOut'), 'Sair')
  assert.equal(translator('es')('shell.signOut'), 'Salir')
  assert.equal(lookup('es', 'shell'), undefined)
  assert.equal(lookup('es', 'shell.nope'), undefined)
  assert.equal(lookup('es', 'shell.signOut.deeper'), undefined)
})
