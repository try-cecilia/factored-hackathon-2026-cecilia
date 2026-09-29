import { createServerFn } from '@tanstack/react-start'
import type { CaseResult, SendResult } from '../chat/types'
import { AgentApiError, agentFetch } from './agent-api'
import { sendChat } from './chat-core'
import { clearSessionToken, getSessionToken } from './session-cookie'

// The model call can take up to LLM_TOTAL_BUDGET_SECONDS (25 s by default) on the API side.
const CHAT_TIMEOUT_MS = 35_000

function parseMessage(input: unknown): { message: string } {
  const { message } = (input ?? {}) as Record<string, unknown>
  if (typeof message !== 'string') throw new Error('message must be text')
  const trimmed = message.trim()
  if (trimmed.length === 0 || trimmed.length > 1000) throw new Error('message must be 1-1000 characters')
  return { message: trimmed }
}

export const sendMessage = createServerFn({ method: 'POST' })
  .validator(parseMessage)
  .handler(({ data }): Promise<SendResult> =>
    sendChat(
      { token: getSessionToken(), clear: clearSessionToken },
      {
        post: (token, message) =>
          agentFetch('/chat', { method: 'POST', body: { session_token: token, message }, timeoutMs: CHAT_TIMEOUT_MS }),
        failureOf: (error) =>
          error instanceof AgentApiError ? { ok: false, failure: error.reason === 'timeout' ? 'timeout' : 'unavailable' } : null,
      },
      data.message,
    ),
  )

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
