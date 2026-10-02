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
  headers?: Record<string, string>
}

function clientIp() {
  const trusted = process.env.TRUSTED_CLIENT_IP_HEADER
  return (trusted && getRequestHeader(trusted)) || getRequestIP()
}

export async function agentFetch(path: string, { method = 'GET', body, token, timeoutMs = 5_000, headers: extra }: RequestOptions = {}) {
  // DEMO_MODE=0 given to the web: its demo functions do nothing, so none reaches the API's sandbox, whoever calls it.
  if (process.env.DEMO_MODE === '0' && path.startsWith('/demo/')) throw new AgentApiError(404)
  const headers = new Headers({ Accept: 'application/json', ...extra })
  const ip = clientIp()
  if (ip) headers.set('X-Client-IP', ip)
  // The API believes a forwarded address only with the secret both services share (api/main.py, client_ip). Set here, after
  // `extra`, so nothing the caller passes can replace it; without the secret configured the address is sent as before.
  const shared = process.env.BFF_CLIENT_IP_SECRET
  if (ip && shared) headers.set('X-BFF-Secret', shared)
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
  if (response.status === 204) return undefined as T
  // An answer that is not JSON breaks the contract: a status, never the parser's message (it quotes the body).
  return (await response.json().catch(() => {
    throw new AgentApiError(502)
  })) as T
}
