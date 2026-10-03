import { createServerFn } from '@tanstack/react-start'
import { AgentApiError, agentApi } from './agent-api'
import { toCustomerContext, type CustomerContext } from './customer-context'
import { deskCall, type Result } from './demo-desk-api'
import { parseDemoDeskAction, resolveResultsOf, withoutNames } from './demo-desk-core'
import { demoConsoleOn } from './demo-gate'
import type { DeskState, Ticket } from './operator.functions'
import { toQueueRow, type QueueRow } from './queue-row'
import { PublicError } from './rpc-guard'
import { sameOriginOnly } from './same-origin'
import { getSessionToken } from './session-cookie'

// The bank's side of the one-click demo: the cases this visitor's session filed, seen and decided as the bank, with the console's
// own screens. The credential is the customer's session cookie and nothing else (demo-desk-api.ts); who acts is "demo", set by the
// API. Every function is off, asking the API for nothing, unless DEMO_CONSOLE=1 (demo-gate.ts): a server function is a public URL.

export type { Result }

/** The desk state of a case as the demo reads it: the console's, plus the predefined result a resolution named. */
export type DemoDeskState = DeskState & { result?: string | null }

/** A case of the demo: the console's ticket, and the results its family may be resolved with (none when it carries an action). */
export type DemoTicket = Omit<Ticket, 'desk'> & { desk: DemoDeskState; resolve_results: string[] }

export type DemoDeskView =
  | { status: 'off' }
  | { status: 'no_session' }
  /** `expiresIn`: the seconds the session has left, as the API counts them (not the browser's clock). */
  | { status: 'active'; customerId: string; sessionRef: string; expiresIn: number }

const OFF = { ok: false, status: 404 } as const

export const getDemoDeskView = createServerFn({ method: 'GET' }).handler(async (): Promise<DemoDeskView> => {
  if (!demoConsoleOn()) return { status: 'off' }
  const token = getSessionToken()
  if (!token) return { status: 'no_session' }
  try {
    const s = await agentApi<{ customer_id: string; session_ref: string; expires_in: number }>('/auth/session', { token })
    return { status: 'active', customerId: s.customer_id, sessionRef: s.session_ref, expiresIn: s.expires_in }
  } catch (error) {
    // A session the API no longer takes is no session; the cookie is left alone, as every passive read does (auth.functions.ts).
    if (error instanceof AgentApiError && error.status === 401) return { status: 'no_session' }
    throw error
  }
})

const idOf = (input: unknown) => {
  const value = (input as Record<string, unknown> | null)?.ticket_id
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{4,64}$/.test(value.trim())) throw new PublicError('ticket_id is not valid')
  return value.trim()
}

// Rows, not tickets, like the console's queue (queue-row.ts).
export const loadDemoQueue = createServerFn({ method: 'GET' }).handler(async (): Promise<Result<QueueRow[]>> => {
  if (!demoConsoleOn()) return OFF
  const result = await deskCall<Ticket[]>('/demo/desk/tickets')
  if (!result.ok) return result
  return Array.isArray(result.data) ? { ok: true, data: result.data.map((t) => toQueueRow({ ...t, desk: withoutNames(t.desk) })) } : { ok: false, status: 502 }
})

export const loadDemoTicket = createServerFn({ method: 'GET' })
  .validator((input: unknown) => ({ id: idOf(input) }))
  .handler(async ({ data }): Promise<Result<DemoTicket>> => {
    if (!demoConsoleOn()) return OFF
    const result = await deskCall<DemoTicket>(`/demo/desk/tickets/${data.id}`)
    if (!result.ok) return result
    return { ok: true, data: { ...result.data, desk: withoutNames(result.data.desk), resolve_results: resolveResultsOf(result.data.resolve_results) } }
  })

export const loadDemoCustomerContext = createServerFn({ method: 'GET' })
  .validator((input: unknown) => ({ id: idOf(input) }))
  .handler(async ({ data }): Promise<Result<CustomerContext>> => {
    if (!demoConsoleOn()) return OFF
    const result = await deskCall<unknown>(`/demo/desk/tickets/${data.id}/customer_context`)
    if (!result.ok) return result
    const context = toCustomerContext(result.data)
    return context ? { ok: true, data: context } : { ok: false, status: 502 }
  })

// A decision is a state change: only from the app's own page (origin-check.ts), on top of the framework's CSRF middleware.
export const actOnDemoTicket = createServerFn({ method: 'POST' })
  .middleware([sameOriginOnly])
  .validator((input: unknown) => ({ ticket_id: idOf(input), ...parseDemoDeskAction(input) }))
  .handler(async ({ data }): Promise<Result<DemoDeskState>> => {
    if (!demoConsoleOn()) return OFF
    const result = await deskCall<DemoDeskState>(`/demo/desk/tickets/${data.ticket_id}/${data.action}`, 'POST', {
      expected_version: data.expected_version,
      reason: data.reason,
      result_code: data.result_code,
      message: data.message,
    })
    return result.ok ? { ok: true, data: withoutNames(result.data) } : result
  })
