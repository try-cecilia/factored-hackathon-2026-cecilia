import assert from 'node:assert/strict'
import { test } from 'node:test'
import { checkOrigin, publicOrigins } from './origin-check.ts'

const post = (url: string, headers: Record<string, string> = {}) => new Request(url, { method: 'POST', headers })
const dev = { production: false }

test('in development, with nothing configured, the origin is the one of the request URL, scheme and port included', () => {
  const url = 'http://127.0.0.1:3127/operador/sesion'
  assert.equal(checkOrigin(post(url, { Origin: 'http://127.0.0.1:3127' }), dev).ok, true)
  assert.equal(checkOrigin(post(url, { Origin: 'https://127.0.0.1:3127' }), dev).ok, false)
  assert.equal(checkOrigin(post(url, { Origin: 'http://127.0.0.1:3000' }), dev).ok, false)
  assert.equal(checkOrigin(post(url, { Referer: 'http://127.0.0.1:3127/operador/login' }), dev).ok, true)
  assert.equal(checkOrigin(post(url, { Referer: 'http://localhost:3127/x' }), dev).ok, false)
})

test('in development a configured origin wins over the request URL', () => {
  const config = { production: false, publicOrigin: 'https://console.bank.example' }
  assert.equal(checkOrigin(post('http://127.0.0.1:3127/x', { Origin: 'https://console.bank.example' }), config).ok, true)
  assert.equal(checkOrigin(post('http://127.0.0.1:3127/x', { Origin: 'http://127.0.0.1:3127' }), config).ok, false)
})

test('a configured value that is not an http(s) origin is a configuration error, in development too', () => {
  const verdict = checkOrigin(post('http://127.0.0.1:3127/x', { Origin: 'http://127.0.0.1:3127' }), { production: false, publicOrigin: 'nope' })
  assert.deepEqual(verdict, { ok: false, reason: 'misconfigured' })
})

test('in production, without a valid public origin, everything is refused as a configuration error', () => {
  for (const publicOrigin of [undefined, '', 'nope']) {
    const verdict = checkOrigin(post('https://console.bank.example/x', { Origin: 'https://console.bank.example' }), { production: true, publicOrigin })
    assert.deepEqual(verdict, { ok: false, reason: 'misconfigured' })
  }
})

test('Fetch Metadata must still say same-origin, and neither header means no proof', () => {
  const config = { production: true, publicOrigin: 'https://console.bank.example' }
  const url = 'https://console.bank.example/operador/sesion'
  assert.equal(checkOrigin(post(url, { 'Sec-Fetch-Site': 'same-site', Origin: 'https://console.bank.example' }), config).ok, false)
  assert.equal(checkOrigin(post(url), config).ok, false)
  assert.equal(checkOrigin(post(url, { 'Sec-Fetch-Site': 'same-origin' }), config).ok, true)
})

test('a comma-separated list trusts each origin in it exactly, and nothing else', () => {
  const config = { production: true, publicOrigin: 'http://127.0.0.1:3000, http://localhost:3000' }
  const url = 'http://localhost:3000/operador/sesion'
  for (const origin of ['http://127.0.0.1:3000', 'http://localhost:3000']) assert.equal(checkOrigin(post(url, { Origin: origin }), config).ok, true, origin)
  assert.equal(checkOrigin(post(url, { Referer: 'http://localhost:3000/operador/login' }), config).ok, true)
  for (const origin of ['http://localhost:3001', 'https://localhost:3000', 'http://127.0.0.2:3000', 'http://[::1]:3000', 'https://attacker.invalid', 'null']) {
    assert.deepEqual(checkOrigin(post(url, { Origin: origin }), config), { ok: false, reason: 'cross-site' }, origin)
  }
})

test('a list with a wildcard, or with any entry that is not an http(s) origin, is a configuration error, not a partial list', () => {
  for (const publicOrigin of ['http://127.0.0.1:3000,*', '*', 'http://127.0.0.1:3000,nope', ',', 'http://127.0.0.1:3000,ftp://x.example']) {
    const verdict = checkOrigin(post('http://127.0.0.1:3000/x', { Origin: 'http://127.0.0.1:3000' }), { production: true, publicOrigin })
    assert.deepEqual(verdict, { ok: false, reason: 'misconfigured' }, publicOrigin)
  }
})

test('publicOrigins normalizes each entry and drops blanks around commas', () => {
  assert.deepEqual(publicOrigins('https://a.example/, http://b.example:8080/x ,'), ['https://a.example', 'http://b.example:8080'])
  assert.equal(publicOrigins(undefined), null)
  assert.equal(publicOrigins(''), null)
})
