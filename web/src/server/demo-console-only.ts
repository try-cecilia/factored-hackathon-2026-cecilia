import { createMiddleware } from '@tanstack/react-start'
import { demoConsoleOn } from './demo-gate'

/**
 * First in the chain of every server function of the one-click demo: with the demo console off (demo-gate.ts) the function does not
 * exist. A real HTTP 404, before the validator runs, so a malformed payload cannot change the answer either, and nothing reaches the API.
 */
export const demoConsoleOnly = createMiddleware({ type: 'function' }).server(({ next }) => {
  if (!demoConsoleOn()) throw new Response('Not Found', { status: 404 })
  return next()
})
