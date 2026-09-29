// The operator console's cookies, like the customer's (cookies-customer.test.ts), follow the origin the browser sees.
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { cookieNamed, flags } from './cookie-helpers.ts'
import { ADMIN, startConsole } from './harness.ts'

const HTTPS = 'https://console.bank.example'
const HTTP = 'http://127.0.0.1:3000'

let app: Awaited<ReturnType<typeof startConsole>>
let origin: string | undefined
before(async () => {
  app = await startConsole()
  origin = process.env.WEB_PUBLIC_ORIGIN
})
after(() => app.close())

const post = (base: string, admin_key: string, headers: Record<string, string> = { Origin: base, 'Sec-Fetch-Site': 'same-origin' }) =>
  app.send('/operador/sesion', { fields: { admin_key }, headers, base })

describe('over plain http (the local Docker stack) the cookies are storable by any browser', () => {
  before(() => void (process.env.WEB_PUBLIC_ORIGIN = HTTP))

  test('the session cookie has no Secure and no __Host- prefix, and stays httpOnly and SameSite=Strict', async () => {
    const res = await post(HTTP, ADMIN)
    assert.equal(res.status, 303)
    const line = cookieNamed(res.headers.getSetCookie(), 'cecilai_operator')
    assert.ok(line, res.headers.getSetCookie().join(' | '))
    assert.ok(line.startsWith('cecilai_operator='), line)
    assert.ok(!flags(line).includes('secure'), line)
    assert.ok(flags(line).includes('httponly') && flags(line).includes('samesite=strict') && flags(line).includes('path=/'), line)
  })

  test('the flash cookie of a refused login has no Secure and no prefix either', async () => {
    const res = await post(HTTP, 'nope')
    const line = cookieNamed(res.headers.getSetCookie(), 'cecilai_operator_flash')
    assert.ok(line, res.headers.getSetCookie().join(' | '))
    assert.ok(line.startsWith('cecilai_operator_flash='), line)
    assert.ok(!flags(line).includes('secure') && flags(line).includes('httponly'), line)
  })

  test('the origin check still refuses a cross-site login and sets nothing', async () => {
    const res = await post(HTTP, ADMIN, { Origin: 'https://attacker.invalid', 'Sec-Fetch-Site': 'cross-site' })
    assert.equal(res.status, 403)
    assert.equal(res.headers.getSetCookie().length, 0)
  })
})

describe('behind https the cookies are Secure with the __Host- prefix', () => {
  before(() => void (process.env.WEB_PUBLIC_ORIGIN = HTTPS))

  test('the session cookie is __Host-, Secure, httpOnly, SameSite=Strict', async () => {
    const res = await post(HTTPS, ADMIN)
    assert.equal(res.status, 303)
    const line = cookieNamed(res.headers.getSetCookie(), 'cecilai_operator')
    assert.ok(line, res.headers.getSetCookie().join(' | '))
    assert.ok(line.startsWith('__Host-cecilai_operator='), line)
    assert.ok(flags(line).includes('secure') && flags(line).includes('httponly') && flags(line).includes('samesite=strict'), line)
  })

  test('the flash cookie of a refused login is __Host- and Secure as well', async () => {
    const res = await post(HTTPS, 'nope')
    const line = cookieNamed(res.headers.getSetCookie(), 'cecilai_operator_flash')
    assert.ok(line, res.headers.getSetCookie().join(' | '))
    assert.ok(line.startsWith('__Host-cecilai_operator_flash='), line)
    assert.ok(flags(line).includes('secure') && flags(line).includes('httponly'), line)
  })
})

describe('the cookie a plain-http login sets is the one the console reads', () => {
  before(() => void (process.env.WEB_PUBLIC_ORIGIN = HTTP))
  after(() => void (process.env.WEB_PUBLIC_ORIGIN = origin))

  test('the cookie the login set does open the console', async () => {
    const res = await post(HTTP, ADMIN)
    const cookie = cookieNamed(res.headers.getSetCookie(), 'cecilai_operator')!.split(';')[0]
    const page = await app.send('/operador/cola', { headers: { Cookie: cookie }, base: HTTP })
    assert.equal(page.status, 200)
  })
})
