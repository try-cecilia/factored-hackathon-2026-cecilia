import { createServerFn } from '@tanstack/react-start'
import type { DemoFault, DemoScenario, DemoTicket } from '../chat/types'
import { AgentApiError, agentApi, agentFetch } from './agent-api'
import { getSessionToken, setSessionToken } from './session-cookie'

// Everything here is the API's DEMO_MODE surface (api/demo.py). Outside the sandbox it answers 404 and the
// front shows nothing: the customer app never depends on it.

type ApiScenario = DemoScenario & { test_pin: string }

async function scenarios(): Promise<ApiScenario[] | null> {
  try {
    return await agentApi<ApiScenario[]>('/demo/scenarios')
  } catch {
    return null
  }
}

export type DemoKit = { enabled: false } | { enabled: true; scenarios: DemoScenario[] }

export const getDemoKit = createServerFn({ method: 'GET' }).handler(
  async (): Promise<DemoKit> => {
    // DEMO_MODE=0 given to the web too (the compose passes the API's): the sandbox is off, so there is nothing to ask.
    if (process.env.DEMO_MODE === '0') return { enabled: false }
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
    if (!found) return { ok: false }
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
    if (!token) return { ok: false }
    try {
      await agentApi('/demo/fault', { method: 'POST', body: { session_token: token, fault: data.fault } })
      return { ok: true }
    } catch (error) {
      if (error instanceof AgentApiError) return { ok: false }
      throw error
    }
  })

export const getDemoTickets = createServerFn({ method: 'GET' }).handler(async (): Promise<DemoTicket[]> => {
  const token = getSessionToken()
  if (!token) return []
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
      created_at: typeof t.created_at === 'number' ? t.created_at : 0,
    }))
  } catch {
    return []
  }
})
