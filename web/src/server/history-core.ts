import type { HistoryEntry, HistoryResult, Reply } from '../chat/types'
import { parseReply, type ChatSession } from './chat-core.ts'

// The read path of the conversation without the framework, like chat-core.ts: the server function wires it to the
// session cookie and agentFetch; tests wire it to fakes. What comes back is what the API rendered for this session.

export type HistoryTransport = {
  get: (token: string) => Promise<{ status: number; json: () => Promise<unknown> }>
}

function parseTurn(raw: unknown): HistoryEntry | null {
  if (typeof raw !== 'object' || raw === null) return null
  const t = raw as Record<string, unknown>
  if (typeof t.text !== 'string' || typeof t.at !== 'number' || !Number.isFinite(t.at)) return null
  const at = Math.round(t.at * 1000)
  if (t.role === 'user') return { role: 'user', text: t.text, at }
  if (t.role !== 'assistant') return null
  // The stored turn has the reply's fields under other names: it goes through the same check as a live reply.
  const reply: Reply | null = parseReply({ ...t, response_text: t.text })
  return reply ? { role: 'assistant', reply, at } : null
}

/** A turn that does not fit the contract is left out; the rest of the conversation still shows. */
export function parseHistory(body: unknown): HistoryEntry[] | null {
  if (!Array.isArray(body)) return null
  return body.flatMap((raw) => parseTurn(raw) ?? [])
}

export async function loadHistory(session: ChatSession, transport: HistoryTransport): Promise<HistoryResult> {
  const token = session.token
  if (!token) return { ok: false, failure: 'session_expired' }
  try {
    const response = await transport.get(token)
    if (response.status === 401) {
      session.clear()
      return { ok: false, failure: 'session_expired' }
    }
    if (response.status < 200 || response.status >= 300) return { ok: false, failure: 'unavailable' }
    const turns = parseHistory(await response.json().catch(() => null))
    return turns ? { ok: true, turns } : { ok: false, failure: 'unavailable' }
  } catch {
    return { ok: false, failure: 'unavailable' }
  }
}
