import type { Disposition, Reply, SendResult, TraceReceipt, Why } from '../chat/types'
import { PublicError } from './rpc-guard.ts'

// The send path without the framework: what the API answered, and what that means for the customer. The server
// function wires it to the session cookie and to agentFetch; tests wire it to fakes.

const DISPOSITIONS: readonly string[] = ['AUTO_RESOLVE', 'CLARIFY', 'ABSTAIN', 'ESCALATE']

function parseTraceReceipt(value: unknown): TraceReceipt | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  const r = value as Record<string, unknown>
  if (typeof r.transaction_id !== 'string' || typeof r.transaction_type !== 'string'
      || typeof r.transaction_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(r.transaction_date)
      || typeof r.amount !== 'number' || !Number.isFinite(r.amount)
      || typeof r.currency !== 'string' || !/^[A-Z]{3}$/.test(r.currency)
      || typeof r.movement_status !== 'string' || typeof r.trace_id !== 'string'
      || typeof r.trace_status !== 'string' || r.read_back !== true
      || typeof r.sla_business_days !== 'number' || !Number.isInteger(r.sla_business_days) || r.sla_business_days < 0) return null
  if (r.data_as_of !== undefined && r.data_as_of !== null
      && (typeof r.data_as_of !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(r.data_as_of))) return null
  if (r.source !== undefined && r.source !== 'account_records') return null
  return r as unknown as TraceReceipt
}

// One turn at a time per session: a second tab or a double click cannot send the same message twice while the
// first is still running. Best effort (one process); the composer also disables itself while sending.
const inFlight = new Set<string>()

export type ChatTransport = {
  // `key` goes to the API as Idempotency-Key: the same key means the same message, whatever number of tries.
  post: (token: string, message: string, key: string) => Promise<{ status: number; json: () => Promise<unknown> }>
  // Says why a request that never got an answer failed: `timeout` (it may have been processed) or not.
  failureOf: (error: unknown) => SendResult | null
}

export const KEY_PATTERN = /^[A-Za-z0-9_-]{8,64}$/

export function parseSend(input: unknown): { message: string; key: string } {
  const { message, key } = (input ?? {}) as Record<string, unknown>
  if (typeof message !== 'string') throw new PublicError('message must be text')
  const trimmed = message.trim()
  if (trimmed.length === 0 || trimmed.length > 1000) throw new PublicError('message must be 1-1000 characters')
  if (typeof key !== 'string' || !KEY_PATTERN.test(key)) throw new PublicError('key must be 8-64 letters, digits, - or _')
  return { message: trimmed, key }
}

// The session is only the token the request carried. A read that finds it rejected says so and leaves the cookie alone: it may be a
// late answer about an old token, and a deletion arriving after a newer login's Set-Cookie would take that login's cookie (as the
// operator's console avoids, operator-session.ts). The next login overwrites the cookie; an explicit sign-out removes it.
export type ChatSession = { token: string | undefined }

export function parseReply(body: unknown): Reply | null {
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
  if (r.degraded === true) reply.degraded = true
  if (r.choice === 'product' || r.choice === 'movement') reply.choice = r.choice
  const traceReceipt = parseTraceReceipt(r.trace_receipt)
  if (traceReceipt) reply.trace_receipt = traceReceipt
  if (typeof r.why === 'object' && r.why !== null) reply.why = r.why as Why
  return reply
}

export async function sendChat(session: ChatSession, transport: ChatTransport, message: string, key: string): Promise<SendResult> {
  const token = session.token
  if (!token) return { ok: false, failure: 'session_expired' }
  if (inFlight.has(token)) return { ok: false, failure: 'busy' }
  inFlight.add(token)
  try {
    const response = await transport.post(token, message, key)
    if (response.status === 401) return { ok: false, failure: 'session_expired' }
    if (response.status === 409) return { ok: false, failure: 'already_processed' }
    if (response.status === 429) return { ok: false, failure: 'rate_limited' }
    if (response.status >= 500) return { ok: false, failure: 'unavailable' }
    if (response.status < 200 || response.status >= 300) return { ok: false, failure: 'unexpected' }
    const body = await response.json().catch(() => null)
    // REAUTH_REQUIRED is not a chat answer: the API says the session is gone.
    if ((body as { disposition?: unknown } | null)?.disposition === 'REAUTH_REQUIRED') return { ok: false, failure: 'session_expired' }
    const reply = parseReply(body)
    return reply ? { ok: true, reply } : { ok: false, failure: 'unexpected' }
  } catch (error) {
    return transport.failureOf(error) ?? { ok: false, failure: 'unexpected' }
  } finally {
    inFlight.delete(token)
  }
}
