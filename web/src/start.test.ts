import assert from 'node:assert/strict'
import { test } from 'node:test'
import { startInstance } from './start.ts'

// The marker the framework puts on the middleware that createCsrfMiddleware makes (start-client-core, outside production).
const csrfSymbol = Symbol.for('tanstack-start:csrf-middleware')

// The framework installs its own CSRF middleware only while the app has no start instance (createStartHandler). This file is the
// app's instance, so the protection of every server function (the customer's sign-in and chat, the operator's decisions) is stated
// here instead of resting on a default: a change that empties this list fails this test and web/tests/http/csrf-actions.test.ts.
test('the start instance registers the CSRF middleware for server functions', async () => {
  const { requestMiddleware } = await startInstance.getOptions()
  assert.ok(requestMiddleware?.some((middleware) => csrfSymbol in middleware), 'no CSRF middleware in requestMiddleware')
})

test('the start instance registers the middleware that makes an unexpected error generic', async () => {
  const { functionMiddleware } = await startInstance.getOptions()
  assert.equal(functionMiddleware?.length, 1)
})
