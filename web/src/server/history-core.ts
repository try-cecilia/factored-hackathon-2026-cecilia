import type { HistoryCase, HistoryEntry, HistoryResult, Reply } from '../chat/types'
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

function parseCase(raw: unknown): HistoryCase | null {
  if (typeof raw !== 'object' || raw === null) return null
  const c = raw as Record<string, unknown>
  if (typeof c.ticket_id !== 'string' || typeof c.category !== 'string' || typeof c.at !== 'number' || !Number.isFinite(c.at)) return null
  return { ticketId: c.ticket_id, category: c.category, at: Math.round(c.at * 1000) }
}

/** A turn or a case that does not fit the contract is left out; the rest of the conversation still shows. */
export function parseHistory(body: unknown): { turns: HistoryEntry[]; cases: HistoryCase[] } | null {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return null
  const { turns, cases } = body as Record<string, unknown>
  if (!Array.isArray(turns)) return null
  return {
    turns: turns.flatMap((raw) => parseTurn(raw) ?? []),
    cases: Array.isArray(cases) ? cases.flatMap((raw) => parseCase(raw) ?? []) : [],
  }
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
    const history = parseHistory(await response.json().catch(() => null))
    return history ? { ok: true, ...history } : { ok: false, failure: 'unavailable' }
  } catch {
    return { ok: false, failure: 'unavailable' }
  }
}
