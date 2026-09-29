import assert from 'node:assert/strict'
import { test } from 'node:test'
import { defaultLocale, htmlLang } from './locales.ts'
import { localeFromAcceptLanguage, resolveLocale } from './resolve.ts'

test('the preference cookie wins over Accept-Language', () => {
  assert.equal(resolveLocale({ cookie: 'pt', acceptLanguage: 'es-AR,es;q=0.9' }), 'pt')
  assert.equal(resolveLocale({ cookie: 'es', acceptLanguage: 'pt-BR' }), 'es')
})

test('without a valid cookie it follows Accept-Language', () => {
  assert.equal(resolveLocale({ acceptLanguage: 'pt-BR,pt;q=0.9,en;q=0.8' }), 'pt')
  assert.equal(resolveLocale({ cookie: 'fr', acceptLanguage: 'pt' }), 'pt')
  assert.equal(resolveLocale({ cookie: '', acceptLanguage: 'es-MX' }), 'es')
})

test('without cookie or a supported language it is Spanish', () => {
  assert.equal(defaultLocale, 'es')
  assert.equal(resolveLocale({}), 'es')
  assert.equal(resolveLocale({ cookie: null, acceptLanguage: null }), 'es')
  assert.equal(resolveLocale({ acceptLanguage: 'en-US,en;q=0.9,fr;q=0.5' }), 'es')
  assert.equal(resolveLocale({ acceptLanguage: '*' }), 'es')
})

test('q weights decide, not the order of the header', () => {
  assert.equal(localeFromAcceptLanguage('es;q=0.4, pt;q=0.8'), 'pt')
  assert.equal(localeFromAcceptLanguage('en, pt;q=0.2, es;q=0.7'), 'es')
})

test('equal weights keep the order the browser sent', () => {
  assert.equal(localeFromAcceptLanguage('pt, es'), 'pt')
  assert.equal(localeFromAcceptLanguage('es-CO, pt-BR'), 'es')
})

test('q=0 means "not acceptable" and is skipped', () => {
  assert.equal(localeFromAcceptLanguage('pt;q=0, es;q=0.1'), 'es')
  assert.equal(localeFromAcceptLanguage('pt;q=0'), undefined)
})

test('junk in the header does not throw', () => {
  assert.equal(localeFromAcceptLanguage(';;;, ,q=x, pt;q=abc'), undefined)
  assert.equal(localeFromAcceptLanguage('PT-br'), 'pt')
  assert.equal(localeFromAcceptLanguage(''), undefined)
})

test('the html lang of Portuguese is the Brazilian variant', () => {
  assert.equal(htmlLang.es, 'es')
  assert.equal(htmlLang.pt, 'pt-BR')
})
