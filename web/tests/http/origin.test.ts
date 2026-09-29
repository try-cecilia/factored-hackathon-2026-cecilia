import assert from 'node:assert/strict'
import { after, before, beforeEach, describe, test } from 'node:test'
import { ADMIN, ORIGIN, sessionCookie, setCookies, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())

const PUBLIC = 'https://console.bank.example'
beforeEach(() => { process.env.WEB_PUBLIC_ORIGIN = PUBLIC })

// The request itself arrives at the public https URL, as it would behind a proxy that terminates TLS and keeps the Host.
const login = (headers: Record<string, string>, base = PUBLIC) => app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers, base })

describe('the origin the forms trust is the configured public one, scheme, host and port', () => {
  test('the exact public origin is accepted, however the browser proves it', async () => {
    const proofs: Record<string, string>[] = [
      { Origin: PUBLIC },
      { Origin: `${PUBLIC}/`, 'Sec-Fetch-Site': 'same-origin' },
      { Referer: `${PUBLIC}/operador/login` },
      { 'Sec-Fetch-Site': 'same-origin' },
    ]
    for (const headers of proofs) {
      const res = await login(headers)
      assert.equal(res.status, 303, JSON.stringify(headers))
      assert.ok(sessionCookie(res), JSON.stringify(headers))
    }
  })

  test('an http page on the same host cannot log a victim into an https console', async () => {
    const attacks: Record<string, string>[] = [
      { Origin: 'http://console.bank.example' },
      { Referer: 'http://console.bank.example/operador/login' },
      { Origin: 'http://console.bank.example', 'Sec-Fetch-Site': 'same-origin' },
    ]
    for (const headers of attacks) {
      const res = await login(headers)
      assert.equal(res.status, 403, JSON.stringify(headers))
      assert.deepEqual(setCookies(res), [], JSON.stringify(headers))
    }
  })

  test('another port or a look-alike host is another origin', async () => {
    const others: Record<string, string>[] = [
      { Origin: 'https://console.bank.example:8443' },
      { Referer: 'https://console.bank.example:8443/x' },
      { Origin: 'https://console.bank.example.attacker.invalid' },
      { Origin: 'https://attacker.invalid' },
    ]
    for (const headers of others) {
      assert.equal((await login(headers)).status, 403, JSON.stringify(headers))
    }
  })

  test('proxy headers do not make an origin ours', async () => {
    const res = await login({ Origin: 'http://console.bank.example', 'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'console.bank.example', Forwarded: 'proto=https;host=console.bank.example' })
    assert.equal(res.status, 403)
  })

  test('the request URL and Host header do not decide it either when a public origin is configured', async () => {
    const res = await login({ Origin: ORIGIN, 'Sec-Fetch-Site': 'same-origin' }, ORIGIN)
    assert.equal(res.status, 403, 'http://console.test is not the configured origin')
  })
})

describe('a list of origins: the local stack answers on 127.0.0.1 and on localhost', () => {
  const LOCAL = ['http://127.0.0.1:3000', 'http://localhost:3000']
  beforeEach(() => { process.env.WEB_PUBLIC_ORIGIN = LOCAL.join(',') })

  for (const origin of LOCAL) {
    test(`${origin} is accepted, and its session cookie opens the console`, async () => {
      const res = await login({ Origin: origin, Referer: `${origin}/operador/login`, 'Sec-Fetch-Site': 'same-origin' }, origin)
      assert.equal(res.status, 303)
      assert.equal(res.headers.get('location'), '/operador/ingreso?to=%2Foperador%2Fcola')
      const cookie = sessionCookie(res)
      assert.ok(cookie)
      assert.equal((await app.send('/operador/cola', { headers: { Cookie: cookie }, base: origin })).status, 200)
    })
  }

  test('another host, another port or another scheme is refused', async () => {
    for (const foreign of ['http://localhost:3001', 'http://127.0.0.1:8000', 'https://localhost:3000', 'http://192.168.1.20:3000', 'https://attacker.invalid']) {
      const res = await login({ Origin: foreign, Referer: `${foreign}/x`, 'Sec-Fetch-Site': 'cross-site' }, LOCAL[0])
      assert.equal(res.status, 403, foreign)
      assert.equal(sessionCookie(res), null, foreign)
    }
  })

  test('proxy headers still do not add an origin to the list', async () => {
    const res = await login({ Origin: 'http://console.bank.example', 'X-Forwarded-Host': 'localhost:3000', 'X-Forwarded-Proto': 'http' }, LOCAL[0])
    assert.equal(res.status, 403)
  })

  test('a wildcard is not an origin: the whole value is refused', async () => {
    process.env.WEB_PUBLIC_ORIGIN = `${LOCAL[0]},*`
    const res = await login({ Origin: LOCAL[0], 'Sec-Fetch-Site': 'same-origin' }, LOCAL[0])
    assert.equal(res.status, 403)
  })
})

describe('in production the public origin is required', () => {
  const errors: string[] = []
  const original = console.error
  beforeEach(() => { errors.length = 0; console.error = (...args: unknown[]) => void errors.push(args.join(' ')) })
  after(() => { console.error = original })

  for (const [name, value] of [['missing', undefined], ['empty', ''], ['not a URL', 'console.bank.example'], ['not http(s)', 'ftp://console.bank.example']] as const) {
    test(`${name}: every form post is refused with a clear log line`, async () => {
      if (value === undefined) delete process.env.WEB_PUBLIC_ORIGIN
      else process.env.WEB_PUBLIC_ORIGIN = value
      const res = await login({ Origin: PUBLIC, 'Sec-Fetch-Site': 'same-origin' })
      assert.equal(res.status, 403)
      assert.deepEqual(setCookies(res), [])
      assert.ok(errors.some((line) => line.includes('WEB_PUBLIC_ORIGIN')), `logged: ${errors.join(' | ')}`)
    })
  }
})
