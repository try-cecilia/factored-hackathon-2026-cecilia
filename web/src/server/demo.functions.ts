import { createServerFn } from '@tanstack/react-start'
import { setCookie } from '@tanstack/react-start/server'
import type { DemoFault, DemoScenario, DemoTicket, DemoTrace } from '../chat/types'
import { localeCookie, localeCookieMaxAge } from '../i18n/locales'
import { cookiePolicy } from './cookie-policy'
import { parseTraces } from './demo-core'
import { entriesOf, parseRole, SCENARIO_OF, type DemoEntry } from './demo-entry'
import { demoConsoleOn } from './demo-gate'
import { createLimiter, perMinuteFromEnv } from './demo-limit'
import { AgentApiError, agentApi, agentFetch, clientIp } from './agent-api'
import { sameOriginOnly } from './same-origin'
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

/**
 * `console` is the one-click demo (the DEMO bar, the entry dialog and the bank's side): only with DEMO_CONSOLE=1 on the web, and
 * then `entries` are the test customers the dialog offers. Left out, there is no console (fail-closed).
 */
export type DemoKit = { enabled: false } | { enabled: true; scenarios: DemoScenario[]; console?: boolean; entries?: DemoEntry[] }

export const getDemoKit = createServerFn({ method: 'GET' }).handler(
  async (): Promise<DemoKit> => {
    const all = await scenarios()
    if (!all) return { enabled: false }
    const desk = demoConsoleOn()
    // The sandbox PINs stay on the server: starting a scenario signs in there.
    return { enabled: true, scenarios: all.map(({ test_pin: _pin, ...scenario }) => scenario), console: desk, entries: desk ? entriesOf(all) : [] }
  },
)

function parseScenarioId(input: unknown): { id: string } {
  const { id } = (input ?? {}) as Record<string, unknown>
  if (typeof id !== 'string' || !/^[a-z0-9_]{1,64}$/.test(id)) throw new Error('invalid scenario id')
  return { id }
}

/**
 * Signs in on the server as a scenario's customer, with the PIN the API gave the server (it never reaches the browser): the previous
 * session is revoked first, the cookie gets the new token, and the scenario's fault is applied. False when any step failed.
 */
async function signInAs(found: ApiScenario): Promise<boolean> {
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
    return true
  } catch {
    return false
  }
}

// A sign-in is a state change: only from the app's own page (origin-check.ts), on top of the framework's CSRF middleware.
export const startScenario = createServerFn({ method: 'POST' })
  .middleware([sameOriginOnly])
  .validator(parseScenarioId)
  .handler(async ({ data }): Promise<{ ok: true; scenario: DemoScenario } | { ok: false }> => {
    const found = (await scenarios())?.find((s) => s.id === data.id)
    if (!found || !(await isPublicAccount(found.customer_id))) return { ok: false }
    if (!(await signInAs(found))) return { ok: false }
    const { test_pin: _pin, ...scenario } = found
    return { ok: true, scenario }
  })

const entryLimiter = createLimiter(() => perMinuteFromEnv(process.env.DEMO_ENTER_RATE_PER_MIN))

export type EnterDemoResult = { ok: true; language: string } | { ok: false; reason: 'off' | 'limited' | 'failed'; retryAfter?: number }

/**
 * The one-click entry: signs in as the role's test customer and leaves the session cookie, so the visitor lands in the chat with no
 * PIN typed. The console demo has no credential of its own: this same cookie is what the bank's side reads with (demo-desk.functions.ts).
 * Off (no API call at all) unless DEMO_CONSOLE=1; limited by address before anything reaches the API.
 */
export const enterDemo = createServerFn({ method: 'POST' })
  .middleware([sameOriginOnly])
  .validator(parseRole)
  .handler(async ({ data }): Promise<EnterDemoResult> => {
    if (!demoConsoleOn()) return { ok: false, reason: 'off' }
    const allowed = entryLimiter.take(clientIp() ?? 'unknown')
    if (!allowed.ok) return { ok: false, reason: 'limited', retryAfter: allowed.retryAfter }
    const found = (await scenarios())?.find((s) => s.id === SCENARIO_OF[data.role])
    if (!found || !(await isPublicAccount(found.customer_id))) return { ok: false, reason: 'failed' }
    if (!(await signInAs(found))) return { ok: false, reason: 'failed' }
    // The customer who speaks Portuguese is seen in Portuguese: the interface follows, like the language switcher would.
    if (found.language === 'pt') setCookie(localeCookie, 'pt', { path: '/', maxAge: localeCookieMaxAge, sameSite: 'lax', secure: cookiePolicy().secure })
    return { ok: true, language: found.language }
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
