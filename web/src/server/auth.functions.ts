import { createServerFn } from '@tanstack/react-start'
import { AgentApiError, agentApi } from './agent-api'
import { clearSessionToken, getSessionToken, setSessionToken } from './session-cookie'
import { PublicError } from './rpc-guard'

export type Credentials = { customer_id: string; pin: string }

export type Session = {
  customer_id: string
  session_ref: string
  segment: string
  country: string
  customer_status: string
  expires_at: number
  expires_in: number
}

export type DemoCustomer = { customer_id: string; test_pin: string }

export type LoginResult = { ok: true } | { ok: false; status: number }

/** `revoked` is whether the API confirmed that it ended the session. The browser has let go of it either way. */
export type LogoutResult = { revoked: boolean }

// The API may be slow or down when the person leaves; the answer, and so the cookie's removal, waits at most this long for it.
const LOGOUT_TIMEOUT_MS = 3_000

function parseCredentials(input: unknown): Credentials {
  const { customer_id, pin } = (input ?? {}) as Record<string, unknown>
  if (typeof customer_id !== 'string' || customer_id.length < 3 || customer_id.length > 32) {
    throw new PublicError('customer_id must be 3-32 characters')
  }
  if (typeof pin !== 'string' || !/^\d{6}$/.test(pin)) throw new PublicError('pin must be 6 digits')
  return { customer_id, pin }
}

export const login = createServerFn({ method: 'POST' })
  .validator(parseCredentials)
  .handler(async ({ data }): Promise<LoginResult> => {
    try {
      const session = await agentApi<{ token: string; expires_in: number }>('/auth/session', {
        method: 'POST',
        body: data,
      })
      setSessionToken(session.token, session.expires_in)
      return { ok: true }
    } catch (error) {
      if (error instanceof AgentApiError) return { ok: false, status: error.status }
      throw error
    }
  })

// Leaving is the person's decision, and it is about THIS browser: the cookie goes always, even when the API could not be asked to
// revoke the session (a 500, no answer, a dropped connection), and whatever else happened while this waited. The answer says whether
// the revocation was confirmed, so the page can tell the truth; when it was not, the token may stay valid in the API until it expires.
// A login of another tab that finished meanwhile is closed in this browser too (the person signs in again, and its token also lives
// until it expires): the server cannot tell it from one whose answer was lost, and that one must not keep the person signed in.
// Only the passive reads leave the cookie alone (chat-core.ts): they are not the person's decision.
export const logout = createServerFn({ method: 'POST' }).handler(async (): Promise<LogoutResult> => {
  const token = getSessionToken()
  if (!token) return { revoked: true }
  const revoked = await agentApi('/auth/session', { method: 'DELETE', token, timeoutMs: LOGOUT_TIMEOUT_MS }).then(
    () => true,
    () => false,
  )
  clearSessionToken()
  return { revoked }
})

export const getSession = createServerFn({ method: 'GET' }).handler(async (): Promise<Session | null> => {
  const token = getSessionToken()
  if (!token) return null
  try {
    const s = await agentApi<Session>('/auth/session', { token })
    return {
      customer_id: s.customer_id,
      session_ref: s.session_ref,
      segment: s.segment,
      country: s.country,
      customer_status: s.customer_status,
      expires_at: s.expires_at,
      expires_in: s.expires_in,
    }
  } catch (error) {
    if (!(error instanceof AgentApiError && error.status === 401)) throw error
    // A rejected token is no session. The cookie is left alone: this may be a late answer about a token a newer login has already
    // replaced (chat-core.ts); the next login overwrites it, and an explicit sign-out removes it.
    return null
  }
})

export const getDemoCustomers = createServerFn({ method: 'GET' }).handler(() =>
  agentApi<DemoCustomer[]>('/demo/customers').catch((): DemoCustomer[] => []),
)
