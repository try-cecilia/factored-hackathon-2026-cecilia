import type { DeskAction } from './operator.functions.ts'
import { PublicError } from './rpc-guard.ts'

// The body of an action of the demo's bank side, checked on the server before it reaches the API (POST /demo/desk/tickets/{id}/{action}).
// The API fixes the actor ("demo") and checks the result against the case's family again: this only keeps out what is not even well
// formed. Free of framework code so a plain `node --test` can run it.

const ACTIONS: readonly DeskAction[] = ['claim', 'approve', 'reject', 'release', 'resolve']
const CODE = /^[a-z0-9_]{1,64}$/

export const RESOLVE_MESSAGE_MAX = 500
const REASON_MAX = 300

const clean = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

/**
 * A resolution is a predefined result of the case's family (`result_code`, required) and, optionally, a message of the person, which
 * the customer reads after it in the fixed frame. A rejection may carry an internal note. Nothing else travels: no operator, no actor.
 */
export function parseDemoDeskAction(input: unknown) {
  const { action, expected_version, reason, result_code, message } = (input ?? {}) as Record<string, unknown>
  if (!ACTIONS.includes(action as DeskAction)) throw new PublicError('action is not valid')
  if (expected_version !== undefined && !(Number.isInteger(expected_version) && (expected_version as number) >= 0)) throw new PublicError('expected_version must be an integer from 0 up')
  const resolving = action === 'resolve'
  const code = clean(result_code)
  if (resolving && !code) throw new PublicError('result_code is required to resolve')
  if (code && !CODE.test(code)) throw new PublicError('result_code is not valid')
  // What the customer reads, kept on one line: the chat shows it as a line of news.
  const text = clean(message).replace(/\s+/g, ' ').slice(0, RESOLVE_MESSAGE_MAX)
  const note = clean(reason).slice(0, REASON_MAX)
  return {
    action: action as DeskAction,
    expected_version: expected_version as number | undefined,
    reason: action === 'reject' ? note || undefined : undefined,
    result_code: resolving ? code : undefined,
    message: resolving ? text || undefined : undefined,
  }
}

/** The results the API offers for a case's family, in its order; anything that is not a code is left out. */
export function resolveResultsOf(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  return [...new Set(raw.filter((code): code is string => typeof code === 'string' && CODE.test(code)))]
}

/** The only actor the demo acts as (api/demo_desk.py ACTOR). */
export const DEMO_ACTOR = 'demo'
/** What the visitor reads in place of the name of anyone else who touched the case (a real operator of the team). */
export const SOMEONE_ELSE = 'banco'

type Named = { operator?: string | null; history?: { operator?: string }[] }

/**
 * A desk state with no name but the demo's own: if a person of the team took or decided a visitor's case, the visitor sees that it
 * was the bank, not who. The API already keeps the name out of its 409s; this covers the state it reads back.
 */
export function withoutNames<T extends Named>(desk: T): T {
  const mask = (name: string | null | undefined) => (name && name !== DEMO_ACTOR ? SOMEONE_ELSE : name)
  return {
    ...desk,
    ...(desk.operator !== undefined && { operator: mask(desk.operator) }),
    ...(Array.isArray(desk.history) && { history: desk.history.map((h) => ({ ...h, operator: mask(h.operator) ?? '' })) }),
  }
}
