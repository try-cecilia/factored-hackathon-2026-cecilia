import { createServerFn } from '@tanstack/react-start'
import type { DemoFault, DemoScenario, DemoTicket, DemoTrace } from '../chat/types'
import { parseTraces } from './demo-core'
import { AgentApiError, agentApi, agentFetch } from './agent-api'
import { getSessionToken, setSessionToken } from './session-cookie'

// Everything here is the API's DEMO_MODE surface (api/demo.py). Outside the sandbox it answers 404 and the
// front shows nothing: the customer app never depends on it.

type ApiScenario = DemoScenario & { test_pin: string }

// DEMO_MODE=0 given to the web too (the compose passes the API's): the sandbox is off, so every function here does nothing and asks
// the API for nothing, however it is called (a server function is a public URL; the panel being hidden stops no one).
const demoOff = () => process.env.DEMO_MODE === '0'

async function scenarios(): Promise<ApiScenario[] | null> {
  if (demoOff()) return null
  try {
    return await agentApi<ApiScenario[]>('/demo/scenarios')
  } catch {
    return null
  }
}

/** Whether the API still lists this account as a public sandbox one: checked when a scenario starts, so a list that has changed since the scenarios were read is not signed in with. */
async function isPublicAccount(customerId: string): Promise<boolean> {
  try {
    return (await agentApi<{ customer_id: string }[]>('/demo/customers')).some((c) => c.customer_id === customerId)
  } catch {
    return false
  }
}

export type DemoKit = { enabled: false } | { enabled: true; scenarios: DemoScenario[] }

export const getDemoKit = createServerFn({ method: 'GET' }).handler(
  async (): Promise<DemoKit> => {
    const all = await scenarios()
    if (!all) return { enabled: false }
    // The sandbox PINs stay on the server: starting a scenario signs in there.
    return { enabled: true, scenarios: all.map(({ test_pin: _pin, ...scenario }) => scenario) }
  },
)

function parseScenarioId(input: unknown): { id: string } {
  const { id } = (input ?? {}) as Record<string, unknown>
  if (typeof id !== 'string' || !/^[a-z0-9_]{1,64}$/.test(id)) throw new Error('invalid scenario id')
  return { id }
}

export const startScenario = createServerFn({ method: 'POST' })
  .validator(parseScenarioId)
  .handler(async ({ data }): Promise<{ ok: true; scenario: DemoScenario } | { ok: false }> => {
    const found = (await scenarios())?.find((s) => s.id === data.id)
    if (!found || !(await isPublicAccount(found.customer_id))) return { ok: false }
    try {
      const previous = getSessionToken()
      if (previous) await agentFetch('/auth/session', { method: 'DELETE', token: previous }).catch(() => undefined)
      const session = await agentApi<{ token: string; expires_in: number }>('/auth/session', {
        method: 'POST',
        body: { customer_id: found.customer_id, pin: found.test_pin },
      })
      setSessionToken(session.token, session.expires_in)
      if (found.fault) {
        await agentApi('/demo/fault', { method: 'POST', body: { session_token: session.token, fault: found.fault } })
      }
      const { test_pin: _pin, ...scenario } = found
      return { ok: true, scenario }
    } catch {
      return { ok: false }
    }
  })

function parseFault(input: unknown): { fault: DemoFault } {
  const { fault } = (input ?? {}) as Record<string, unknown>
  if (fault !== 'expire_session' && fault !== 'llm_outage' && fault !== 'llm_restore') throw new Error('invalid fault')
  return { fault }
}

export const applyDemoFault = createServerFn({ method: 'POST' })
  .validator(parseFault)
  .handler(async ({ data }): Promise<{ ok: boolean }> => {
    const token = getSessionToken()
    if (demoOff() || !token) return { ok: false }
    try {
      await agentApi('/demo/fault', { method: 'POST', body: { session_token: token, fault: data.fault } })
      return { ok: true }
    } catch (error) {
      if (error instanceof AgentApiError) return { ok: false }
      throw error
    }
  })

/** A text's code with its parameters, as the API sends it; anything else is no code, and the text shows as it came. */
function textCode(value: unknown): NonNullable<DemoTicket['reason_code']> | null {
  if (!value || typeof value !== 'object') return null
  const { code, params } = value as { code?: unknown; params?: unknown }
  if (typeof code !== 'string') return null
  const plain = params && typeof params === 'object' && !Array.isArray(params)
  return { code, params: plain ? (params as Record<string, string | number>) : undefined }
}

export const getDemoTickets = createServerFn({ method: 'GET' }).handler(async (): Promise<DemoTicket[]> => {
  const token = getSessionToken()
  if (demoOff() || !token) return []
  try {
    const tickets = await agentApi<Record<string, unknown>[]>('/demo/tickets', { method: 'POST', body: { session_token: token } })
    return tickets.map((t) => ({
      ticket_id: String(t.ticket_id),
      queue: String(t.queue ?? ''),
      priority: String(t.priority ?? ''),
      category: String(t.category ?? ''),
      request: String(t.request ?? ''),
      reason: String(t.reason ?? ''),
      suggested_next_step: String(t.suggested_next_step ?? ''),
      open_questions: Array.isArray(t.open_questions) ? t.open_questions.map(String) : [],
      reason_code: textCode(t.reason_code),
      open_question_codes: Array.isArray(t.open_question_codes) ? t.open_question_codes.map(textCode) : undefined,
      next_step_code: typeof t.next_step_code === 'string' ? t.next_step_code : null,
      created_at: typeof t.created_at === 'number' ? t.created_at : 0,
    }))
  } catch {
    return []
  }
})

export const getDemoTraces = createServerFn({ method: 'GET' }).handler(async (): Promise<DemoTrace[]> => {
  const token = getSessionToken()
  if (demoOff() || !token) return []
  try {
    return parseTraces(await agentApi<unknown>('/demo/traces', { method: 'POST', body: { session_token: token } }))
  } catch {
    return []
  }
})
