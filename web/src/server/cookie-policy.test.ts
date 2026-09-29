import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { cookiePolicy } from './cookie-policy.ts'

const policy = (env: Record<string, string | undefined>) => {
  const { secure, name } = cookiePolicy(env)
  return { secure, session: name('cecilai_session') }
}

describe('cookie policy: Secure and __Host- follow the public origin, not NODE_ENV', () => {
  test('an https origin gets Secure and the __Host- prefix, in production or not', () => {
    for (const NODE_ENV of ['production', 'development', undefined]) {
      assert.deepEqual(policy({ NODE_ENV, WEB_PUBLIC_ORIGIN: 'https://console.bank.example' }), { secure: true, session: '__Host-cecilai_session' })
    }
  })

  test('an http origin gets neither, even in production (the Docker image runs there)', () => {
    for (const origin of ['http://127.0.0.1:3000', 'http://localhost:3000', 'http://192.168.1.20:3000']) {
      assert.deepEqual(policy({ NODE_ENV: 'production', WEB_PUBLIC_ORIGIN: origin }), { secure: false, session: 'cecilai_session' })
    }
  })

  test('without an origin, production keeps Secure and the prefix; development has neither', () => {
    assert.deepEqual(policy({ NODE_ENV: 'production' }), { secure: true, session: '__Host-cecilai_session' })
    assert.deepEqual(policy({ NODE_ENV: 'production', WEB_PUBLIC_ORIGIN: '' }), { secure: true, session: '__Host-cecilai_session' })
    assert.deepEqual(policy({ NODE_ENV: 'development' }), { secure: false, session: 'cecilai_session' })
    assert.deepEqual(policy({}), { secure: false, session: 'cecilai_session' })
  })

  test('a value that is not an http(s) origin does not loosen production', () => {
    for (const bad of ['not a url', 'ftp://console.bank.example', 'console.bank.example']) {
      assert.equal(policy({ NODE_ENV: 'production', WEB_PUBLIC_ORIGIN: bad }).secure, true, bad)
    }
  })

  test('surrounding spaces in the origin do not change the decision', () => {
    assert.equal(policy({ NODE_ENV: 'production', WEB_PUBLIC_ORIGIN: ' http://127.0.0.1:3000 ' }).secure, false)
  })

  test('the prefix is applied to any cookie name the same way', () => {
    assert.equal(cookiePolicy({ WEB_PUBLIC_ORIGIN: 'https://x.example' }).name('cecilai_operator_flash'), '__Host-cecilai_operator_flash')
    assert.equal(cookiePolicy({ WEB_PUBLIC_ORIGIN: 'http://x.example' }).name('cecilai_operator_flash'), 'cecilai_operator_flash')
  })
})
