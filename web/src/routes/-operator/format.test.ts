import assert from 'node:assert/strict'
import { test } from 'node:test'
import { es } from '../../i18n/es.ts'
import { pt } from '../../i18n/pt.ts'
import { translator } from '../../i18n/translate.ts'
import { ageShort, ago, categoryName, dispositionName, explainKey, money, shortStamp } from './format.ts'

const now = Date.UTC(2026, 8, 29, 12, 0, 0)
const at = (secondsAgo: number) => now / 1000 - secondsAgo

test('ageShort uses m, h and d, and never goes negative', () => {
  assert.equal(ageShort(at(20), now), '<1m')
  assert.equal(ageShort(at(4 * 60 + 5), now), '4m')
  assert.equal(ageShort(at(3600), now), '1h')
  assert.equal(ageShort(at(26 * 3600), now), '1d')
  assert.equal(ageShort(at(-500), now), '<1m')
  assert.equal(ageShort(null, now), '—')
})

test('ago reads in the language of the interface', () => {
  assert.equal(ago(at(4 * 60), 'es', now), 'hace 4 minutos')
  assert.equal(ago(at(4 * 60), 'pt', now), 'há 4 minutos')
})

test('a known category is translated, an unknown one is shown as it came, a missing one is a dash', () => {
  assert.equal(categoryName(translator(es), 'fraud'), 'Fraude')
  assert.equal(categoryName(translator(pt), 'account_takeover'), 'Invasão de conta')
  assert.equal(categoryName(translator(es), 'brand_new'), 'brand_new')
  assert.equal(categoryName(translator(es), 'toString'), 'toString')
  assert.equal(categoryName(translator(es), null), '—')
  assert.equal(dispositionName(translator(es), 'ESCALATE'), 'Derivado')
})

test('money and evidence stamps', () => {
  assert.equal(money(8450, 'MXN'), '8,450.00 MXN')
  assert.equal(money('199', 'USD'), '199.00 USD')
  assert.equal(money(undefined, 'USD'), '— USD')
  assert.equal(shortStamp('2026-09-28T14:02:11'), '09-28 14:02')
  assert.equal(shortStamp('2026-09-28'), '09-28')
  assert.equal(shortStamp(null), '—')
})

test('each failure status maps to a key, and a failed action reads differently from a failed read', () => {
  assert.equal(explainKey(401, true), 'operator.errors.expiredActing')
  assert.equal(explainKey(401), 'operator.errors.expired')
  assert.equal(explainKey(404, true), 'operator.errors.notFoundActing')
  assert.equal(explainKey(409), 'operator.errors.conflict')
  assert.equal(explainKey(500), 'operator.errors.generic')
})

test('every disposition a turn can end with has a name in both languages, never the raw code', () => {
  // AUTO_RESOLVE, CLARIFY, ABSTAIN and ESCALATE come from agent/policy/router.py; REAUTH_REQUIRED from agent/core/orchestrator.py.
  for (const code of ['AUTO_RESOLVE', 'CLARIFY', 'ABSTAIN', 'ESCALATE', 'REAUTH_REQUIRED']) {
    for (const locale of ['es', 'pt'] as const) assert.notEqual(dispositionName(translator({ es, pt }[locale]), code), code, `${code} in ${locale}`)
  }
  assert.equal(dispositionName(translator(es), 'REAUTH_REQUIRED'), 'Reingreso requerido')
  assert.equal(dispositionName(translator(pt), 'REAUTH_REQUIRED'), 'Novo acesso necessário')
  assert.equal(dispositionName(translator(es), 'SOMETHING_NEW'), 'SOMETHING_NEW')
})
