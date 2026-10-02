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

export const logout = createServerFn({ method: 'POST' }).handler(async () => {
  const token = getSessionToken()
  if (token) await agentApi('/auth/session', { method: 'DELETE', token })
  clearSessionToken()
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
    clearSessionToken()
    return null
  }
})

export const getDemoCustomers = createServerFn({ method: 'GET' }).handler(() =>
  agentApi<DemoCustomer[]>('/demo/customers').catch((): DemoCustomer[] => []),
)
