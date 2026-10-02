import '@tanstack/react-start/server-only'
import { agentFetch } from './agent-api'
import { getOperatorSession, invalidateOperatorSession, operatorSessionId } from './operator-session'

// What every operator server function returns: the data, or the HTTP status the UI should explain.
// 0 = no BFF session; 403 = the session has no operator key (reading is allowed, acting is not).
export type Result<T> = { ok: true; data: T } | { ok: false; status: number; message?: string }

const PUBLIC_DETAIL = new Set([400, 409])

async function call<T>(path: string, headers: Record<string, string>, method: 'GET' | 'POST', body?: unknown): Promise<Result<T>> {
  const response = await agentFetch(path, { method, body, headers }).catch(() => null)
  if (!response) return { ok: false, status: 503 }
  if (!response.ok) {
    // The API's own words travel only for the answers the console shows to the operator: a 400 (what is wrong with the action) and a
    // 409 (what changed under it). Of any other status, such as a 5xx, only the status leaves: its detail is a diagnosis for the server.
    if (!PUBLIC_DETAIL.has(response.status)) return { ok: false, status: response.status }
    const failure = (await response.json().catch(() => null)) as { detail?: unknown } | null
    return { ok: false, status: response.status, message: typeof failure?.detail === 'string' ? failure.detail : undefined }
  }
  // A 2xx that is not JSON breaks the contract: 502 for the console to explain, never the parser's message (it quotes the body).
  const data = await response.json().then((body: T) => ({ body }), () => null)
  return data ? { ok: true, data: data.body } : { ok: false, status: 502 }
}

/** A read with the session's admin key; `touch` is false for the automatic refresh. A rejected key ends that session on the server. */
export async function adminRead<T>(path: string, touch: boolean): Promise<Result<T>> {
  const id = operatorSessionId() // which session this request used, taken before waiting on the API
  const session = getOperatorSession(touch)
  if (!session) return { ok: false, status: 0 }
  const result = await call<T>(path, { 'X-Admin-Key': session.adminKey }, 'GET')
  // Only that session is ended, and without a Set-Cookie: a late 401 must not delete the cookie of a newer login.
  if (!result.ok && result.status === 401) invalidateOperatorSession(id)
  return result
}

/** An action with the session's operator key. A rejected key is dropped so the UI asks for it again. */
export async function operatorAct<T>(path: string, body: unknown): Promise<Result<T>> {
  const session = getOperatorSession(true) // an action is always the person
  if (!session) return { ok: false, status: 0 }
  if (!session.operatorKey) return { ok: false, status: 403 }
  const result = await call<T>(path, { 'X-Operator-Key': session.operatorKey }, 'POST', body)
  if (!result.ok && result.status === 401) {
    session.operatorKey = undefined
    session.operator = undefined
  }
  return result
}

export const probeAdminKey = (key: string) => call<unknown>('/admin/llm_budget', { 'X-Admin-Key': key }, 'GET')
export const probeOperatorKey = (key: string) => call<{ operator: string }>('/admin/operator/me', { 'X-Operator-Key': key }, 'GET')
