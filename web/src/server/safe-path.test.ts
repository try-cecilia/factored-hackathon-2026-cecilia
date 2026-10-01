import assert from 'node:assert/strict'
import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { CUSTOMER_DESTINATIONS, customerDestination } from './safe-path.ts'

describe('the pages a customer is sent on to after signing in', () => {
  test('are the routes behind the session, none more and none less', () => {
    const authed = readdirSync(join(import.meta.dirname, '../routes/_authed')).map((f) => '/' + f.replace(/\.tsx?$/, ''))
    assert.deepEqual([...CUSTOMER_DESTINATIONS].sort(), authed.sort())
  })

  test('keep their query and fragment, and a trailing slash is dropped', () => {
    assert.equal(customerDestination('/chat?x=1#foo'), '/chat?x=1#foo')
    assert.equal(customerDestination('/chat/?x=1'), '/chat?x=1')
  })

  test('nothing else is one: other pages of this site, the console, the login, or anything off the site', () => {
    for (const value of ['/@evil.invalid', '/nada', '/operador/cola', '/login', '/', '/chat/x', '/Chat', '//evil.invalid', 'https://evil.invalid', 'javascript:alert(1)', undefined, 3]) {
      assert.equal(customerDestination(value), undefined, String(value))
    }
  })
})
