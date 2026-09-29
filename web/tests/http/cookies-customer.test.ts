// What the sign-in sets in the browser depends on the origin the browser sees (WEB_PUBLIC_ORIGIN), not on NODE_ENV: the build
// runs in production mode both here and in the Docker image, and Safari drops a Secure / __Host- cookie sent over plain http.
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { cookieNamed, flags } from './cookie-helpers.ts'
import { startCustomerApp } from './customer-harness.ts'

const HTTPS = 'https://console.bank.example'
const HTTP = 'http://127.0.0.1:3000'

let customer: Awaited<ReturnType<typeof startCustomerApp>>
let origin: string | undefined
before(async () => {
  customer = await startCustomerApp(() => false)
  origin = process.env.WEB_PUBLIC_ORIGIN
})
after(() => customer.close())

describe('over plain http (the local Docker stack) the cookies are storable by any browser', () => {
  before(() => void (process.env.WEB_PUBLIC_ORIGIN = HTTP))

  test('the customer session cookie has no Secure and no __Host- prefix, and keeps httpOnly and SameSite', async () => {
    const res = await customer.signIn(HTTP)
    const line = cookieNamed(res.headers.getSetCookie(), 'cecilai_session')
    assert.ok(line, `set-cookie: ${res.headers.getSetCookie().join(' | ')}`)
    assert.ok(line.startsWith('cecilai_session='), line)
    assert.ok(!flags(line).includes('secure'), line)
    assert.ok(flags(line).includes('httponly') && flags(line).includes('samesite=lax') && flags(line).includes('path=/'), line)
  })
})

describe('behind https the cookies are Secure with the __Host- prefix', () => {
  before(() => void (process.env.WEB_PUBLIC_ORIGIN = HTTPS))

  test('the customer session cookie is __Host-, Secure, httpOnly, SameSite=Lax', async () => {
    const res = await customer.signIn(HTTPS)
    const line = cookieNamed(res.headers.getSetCookie(), 'cecilai_session')
    assert.ok(line, res.headers.getSetCookie().join(' | '))
    assert.ok(line.startsWith('__Host-cecilai_session='), line)
    assert.ok(flags(line).includes('secure') && flags(line).includes('httponly') && flags(line).includes('samesite=lax') && flags(line).includes('path=/'), line)
  })
})

describe('without WEB_PUBLIC_ORIGIN, production keeps Secure', () => {
  before(() => void delete process.env.WEB_PUBLIC_ORIGIN)
  after(() => void (process.env.WEB_PUBLIC_ORIGIN = origin))

  test('the customer session cookie is __Host- and Secure', async () => {
    const res = await customer.signIn(HTTPS)
    const line = cookieNamed(res.headers.getSetCookie(), 'cecilai_session')
    assert.ok(line, res.headers.getSetCookie().join(' | '))
    assert.ok(line.startsWith('__Host-cecilai_session=') && flags(line).includes('secure'), line)
  })
})
