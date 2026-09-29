import type { AnyRouter } from '@tanstack/react-router'
import type { Result, Ticket } from '../../server/operator.functions'

/**
 * Turns a read that threw (the browser could not reach the BFF) into the same typed failure the BFF returns when it cannot
 * reach the API. A thrown loader would put the whole route in error, unmounting the panel and its 409 notice, and the router
 * keeps the old loader data next to that error.
 */
export const guarded = <T>(read: () => Promise<Result<T>>): Promise<Result<T>> => read().catch((): Result<T> => ({ ok: false, status: 503 }))

/**
 * Reads the case again and says whether that worked. Before the caller lifts a 409 lock: every match of the chain ended in
 * success (a route that failed keeps the previous data of its children, so the parents count too), the data is the case that
 * was asked for, and its version is not older than the one already on screen.
 */
export async function readAgain(router: AnyRouter, routeId: string, ticketId: string, minVersion: number): Promise<boolean> {
  try {
    await router.invalidate()
  } catch {
    return false
  }
  if (router.state.matches.some((m) => m.status !== 'success')) return false
  const match = router.state.matches.find((m) => m.routeId === routeId)
  if (!match) return false
  const result = match.loaderData as Result<Ticket> | undefined
  return result?.ok === true && result.data.ticket_id === ticketId && result.data.desk.version >= minVersion
}
