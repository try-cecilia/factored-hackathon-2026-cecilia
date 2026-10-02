// What a server function may say to the browser when it fails. The framework puts a thrown Error's message on the wire, so a parser
// error that quotes the API's body, or a TypeError that names one of our fields, would travel to the page. The rule is an allow
// list: only a PublicError (the validators' "that input is not valid") keeps its message; anything else the browser sees as
// GENERIC_ERROR. Free of framework code so a plain `node --test` can run it; fail-safe.ts is the middleware that applies it.

export class PublicError extends Error {}

export const GENERIC_ERROR = 'internal error'

// What the framework throws to steer, not to fail: a Response (a redirect is one) and a not-found marker go through untouched.
const steering = (error: unknown) => error instanceof Response || (typeof error === 'object' && error !== null && (error as { isNotFound?: unknown }).isNotFound === true)

/** The error the browser gets for `error`; the diagnosis stays on the server as the kind of failure, never its message or the API's body. */
export function toClientError(error: unknown): unknown {
  if (error instanceof PublicError || steering(error)) return error
  console.error(`[rpc] unexpected ${error instanceof Error ? error.name : typeof error}`)
  return new Error(GENERIC_ERROR)
}
