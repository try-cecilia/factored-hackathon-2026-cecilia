import { createServerFn } from '@tanstack/react-start'
import type { CaseResult, Disposition, Reply, SendResult, Why } from '../chat/types'
import { AgentApiError, agentFetch } from './agent-api'
import { clearSessionToken, getSessionToken } from './session-cookie'

// The model call can take up to LLM_TOTAL_BUDGET_SECONDS (25 s by default) on the API side.
const CHAT_TIMEOUT_MS = 35_000
const DISPOSITIONS: readonly string[] = ['AUTO_RESOLVE', 'CLARIFY', 'ABSTAIN', 'ESCALATE']

// One turn at a time per session: a second tab or a double click cannot send the same message twice while the
// first is still running. Best effort (one process); the composer also disables itself while sending.
const inFlight = new Set<string>()

function parseMessage(input: unknown): { message: string } {
  const { message } = (input ?? {}) as Record<string, unknown>
  if (typeof message !== 'string') throw new Error('message must be text')
  const trimmed = message.trim()
  if (trimmed.length === 0 || trimmed.length > 1000) throw new Error('message must be 1-1000 characters')
  return { message: trimmed }
}

function parseReply(body: unknown): Reply | null {
  if (typeof body !== 'object' || body === null) return null
  const r = body as Record<string, unknown>
  if (typeof r.response_text !== 'string' || typeof r.trace_id !== 'string') return null
  if (typeof r.disposition !== 'string' || !DISPOSITIONS.includes(r.disposition)) return null
  const reply: Reply = {
    trace_id: r.trace_id,
    disposition: r.disposition as Disposition,
    response_text: r.response_text,
    language: typeof r.language === 'string' ? r.language : 'es',
    category: typeof r.category === 'string' ? r.category : '',
    ticket_id: typeof r.ticket_id === 'string' ? r.ticket_id : null,
    latency_ms: typeof r.latency_ms === 'number' ? r.latency_ms : 0,
  }
  if (typeof r.why === 'object' && r.why !== null) reply.why = r.why as Why
  return reply
}

export const sendMessage = createServerFn({ method: 'POST' })
  .validator(parseMessage)
  .handler(async ({ data }): Promise<SendResult> => {
    const token = getSessionToken()
    if (!token) return { ok: false, failure: 'session_expired' }
    if (inFlight.has(token)) return { ok: false, failure: 'busy' }
    inFlight.add(token)
    try {
      const response = await agentFetch('/chat', {
        method: 'POST',
        body: { session_token: token, message: data.message },
        timeoutMs: CHAT_TIMEOUT_MS,
      })
      if (response.status === 429) return { ok: false, failure: 'rate_limited' }
      if (response.status >= 500) return { ok: false, failure: 'unavailable' }
      if (!response.ok) return { ok: false, failure: 'unexpected' }
      const body = await response.json().catch(() => null)
      // REAUTH_REQUIRED is not a chat answer: the API says the session is gone.
      if ((body as { disposition?: unknown } | null)?.disposition === 'REAUTH_REQUIRED') {
        clearSessionToken()
        return { ok: false, failure: 'session_expired' }
      }
      const reply = parseReply(body)
      return reply ? { ok: true, reply } : { ok: false, failure: 'unexpected' }
    } catch (error) {
      if (error instanceof AgentApiError) return { ok: false, failure: error.reason === 'timeout' ? 'timeout' : 'unavailable' }
      return { ok: false, failure: 'unexpected' }
    } finally {
      inFlight.delete(token)
    }
  })

function parseTicketId(input: unknown): { ticket_id: string } {
  const { ticket_id } = (input ?? {}) as Record<string, unknown>
  if (typeof ticket_id !== 'string' || !/^[A-Za-z0-9-]{8,64}$/.test(ticket_id)) throw new Error('invalid ticket id')
  return { ticket_id }
}

export const getCase = createServerFn({ method: 'GET' })
  .validator(parseTicketId)
  .handler(async ({ data }): Promise<CaseResult> => {
    const token = getSessionToken()
    if (!token) return { ok: false, failure: 'session_expired' }
    try {
      const response = await agentFetch(`/case/${data.ticket_id}`, { token })
      if (response.status === 401) {
        clearSessionToken()
        return { ok: false, failure: 'session_expired' }
      }
      if (response.status === 404) return { ok: false, failure: 'not_found' }
      if (!response.ok) return { ok: false, failure: 'unavailable' }
      const body = (await response.json().catch(() => null)) as Record<string, unknown> | null
      if (!body || typeof body.status !== 'string') return { ok: false, failure: 'unavailable' }
      return {
        ok: true,
        case: {
          ticket_id: data.ticket_id,
          status: body.status,
          message: typeof body.message === 'string' ? body.message : null,
        },
      }
    } catch {
      return { ok: false, failure: 'unavailable' }
    }
  })
