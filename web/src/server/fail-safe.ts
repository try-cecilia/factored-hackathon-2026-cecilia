import { createMiddleware } from '@tanstack/react-start'
import { toClientError } from './rpc-guard.ts'

/** For every server function (src/start.ts): an unexpected error leaves as a generic one, see rpc-guard.ts. */
export const failSafe = createMiddleware({ type: 'function' }).server(async ({ next }) => {
  try {
    return await next()
  } catch (error) {
    throw toClientError(error)
  }
})
