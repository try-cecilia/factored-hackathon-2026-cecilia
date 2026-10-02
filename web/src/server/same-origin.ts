import { createMiddleware } from '@tanstack/react-start'
import { getRequest } from '@tanstack/react-start/server'
import { checkOrigin, originConfigFromEnv } from './origin-check.ts'

/**
 * For the server functions that act for the operator: the call must prove it comes from the console's own origin, by the rules of the
 * console's forms (origin-check.ts), which are stricter than the framework's CSRF middleware (that one lets `Sec-Fetch-Site:
 * same-origin` through whatever Origin says). A refused call is a 403 before the handler runs: no session touched, nothing sent to the API.
 */
export const sameOriginOnly = createMiddleware({ type: 'function' }).server(({ next }) => {
  if (!checkOrigin(getRequest(), originConfigFromEnv()).ok) throw new Response('Forbidden', { status: 403 })
  return next()
})
