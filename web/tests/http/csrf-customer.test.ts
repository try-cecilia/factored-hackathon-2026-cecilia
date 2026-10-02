// The customer's sign-in is a TanStack Start server function, not a form: it has no origin check of ours (origin-check.ts guards the
// operator forms). What stops a foreign page from posting it is the framework's default CSRF middleware for server functions
// (createStartHandler, @tanstack/start-server-core), which refuses a call that is not from the same origin. This pins that behaviour
// on the sign-in function, so an upgrade that drops it fails here instead of silently leaving SameSite=Lax as the only guard.
import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import { ORIGIN, startCustomerApp } from './customer-harness.ts'

let customer: Awaited<ReturnType<typeof startCustomerApp>>
before(async () => { customer = await startCustomerApp(() => false) })
after(() => customer.close())

const signInsReachingTheApi = () => customer.seen.filter((r) => r.url === '/auth/session').length

describe('a call to the customer sign-in that does not come from the app\'s own origin', () => {
  test('is a 403 that sets no cookie and never reaches the agent API', async () => {
    const refused: Record<string, string>[] = [
      { 'Sec-Fetch-Site': 'cross-site' },
      { 'Sec-Fetch-Site': 'same-site' }, // a sibling subdomain
      { 'Sec-Fetch-Site': 'none' },
      { Origin: 'https://attacker.invalid' },
      { Origin: 'null' },
      { Origin: 'https://attacker.invalid', 'Sec-Fetch-Site': 'cross-site' },
      {}, // neither header: no proof of origin
    ]
    for (const proof of refused) {
      const before = signInsReachingTheApi()
      const res = await customer.signIn(ORIGIN, proof)
      assert.equal(res.status, 403, JSON.stringify(proof))
      assert.deepEqual(res.headers.getSetCookie(), [], JSON.stringify(proof))
      assert.equal(signInsReachingTheApi(), before, `${JSON.stringify(proof)} reached the API`)
    }
  })

  test('the same call from the app\'s own page works', async () => {
    const res = await customer.signIn(ORIGIN)
    assert.equal(res.status, 200)
    assert.ok(res.headers.getSetCookie().some((c) => c.includes('cecilai_session=')))
  })
})
