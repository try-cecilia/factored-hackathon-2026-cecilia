import '@tanstack/react-start/server-only'
import { agentFetch } from './agent-api'
import { getSessionToken } from './session-cookie'

// How the demo's bank side talks to the API (/demo/desk/*). Its only credential is the customer's own session cookie, sent as
// X-Session-Token: no admin or operator key exists on this path, and this file never imports the operator's session or its API
// client (a shape test pins it). The API filters every read by that session; the rules for what reaches the browser are the
// console's: the detail only of a 400 (what is wrong with the action) or a 409 (what changed under it), the status of anything else.

/** The data, or the HTTP status the UI explains. 0 = no session cookie at all. */
export type Result<T> = { ok: true; data: T } | { ok: false; status: number; message?: string }

const PUBLIC_DETAIL = new Set([400, 409])

export async function deskCall<T>(path: string, method: 'GET' | 'POST' = 'GET', body?: unknown): Promise<Result<T>> {
  const token = getSessionToken()
  if (!token) return { ok: false, status: 0 }
  const response = await agentFetch(path, { method, body, token }).catch(() => null)
  if (!response) return { ok: false, status: 503 }
  // A 401 is a session the API no longer takes: the cookie is left alone (a passive read is not the person's decision, chat-core.ts).
  if (!response.ok) {
    if (!PUBLIC_DETAIL.has(response.status)) return { ok: false, status: response.status }
    const failure = (await response.json().catch(() => null)) as { detail?: unknown } | null
    return { ok: false, status: response.status, message: typeof failure?.detail === 'string' ? failure.detail : undefined }
  }
  // A 2xx that is not JSON breaks the contract: 502, never the parser's message (it quotes the body).
  const data = await response.json().then((parsed: T) => ({ parsed }), () => null)
  return data ? { ok: true, data: data.parsed } : { ok: false, status: 502 }
}
