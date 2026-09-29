import '@tanstack/react-start/server-only'
import { getRequestHeader, getRequestIP } from '@tanstack/react-start/server'

export class AgentApiError extends Error {
  // `timeout` means the request may have been processed; `network` means it never reached the API.
  constructor(readonly status: number, readonly reason?: 'timeout' | 'network') {
    super(`agent API responded ${status}`)
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: unknown
  token?: string
  timeoutMs?: number
}

function clientIp() {
  const trusted = process.env.TRUSTED_CLIENT_IP_HEADER
  return (trusted && getRequestHeader(trusted)) || getRequestIP()
}

export async function agentFetch(path: string, { method = 'GET', body, token, timeoutMs = 5_000 }: RequestOptions = {}) {
  const headers = new Headers({ Accept: 'application/json' })
  const ip = clientIp()
  if (ip) headers.set('X-Client-IP', ip)
  if (token) headers.set('X-Session-Token', token)
  if (body !== undefined) headers.set('Content-Type', 'application/json')

  try {
    return await fetch(new URL(path, process.env.AGENT_API_URL || 'http://127.0.0.1:8000'), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch (error) {
    throw new AgentApiError(503, error instanceof Error && error.name === 'TimeoutError' ? 'timeout' : 'network')
  }
}

export async function agentApi<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await agentFetch(path, options)
  if (!response.ok) throw new AgentApiError(response.status)
  return (response.status === 204 ? undefined : await response.json()) as T
}
