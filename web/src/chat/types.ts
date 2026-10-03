// Shapes the chat server functions hand to the browser. The session token is never part of them.

export type Disposition = 'AUTO_RESOLVE' | 'CLARIFY' | 'ABSTAIN' | 'ESCALATE'

// DEMO_MODE only: what api/demo.py explains about one reply.
export type Why = {
  rule: string
  because: { en: string; es: string; pt?: string }
  model: {
    called: boolean
    provider: string | null
    model: string | null
    saw: string | null
    chose: { tool: string; args: Record<string, string | number | boolean | null> }[]
  }
  checks: { tool: string; product: string | null; ok: boolean; outcome: string }[]
  llm_calls: number
  cost_usd: number | null
  latency_ms: number
}

export type Reply = {
  trace_id: string
  disposition: Disposition
  response_text: string
  language: string
  category: string
  ticket_id: string | null
  latency_ms: number
  /** Limited mode: the model was unavailable and the code answered alone. */
  degraded?: boolean
  /** What the numbered options of a clarification are: a product (answered by name) or a pending movement (answered by number). */
  choice?: 'product' | 'movement'
  trace_receipt?: TraceReceipt
  why?: Why
}

/** Safe, customer-facing facts from a movement revalidated and a trace request read back by the service. */
export type TraceReceipt = {
  transaction_id: string
  transaction_type: string
  transaction_date: string
  amount: number
  currency: string
  movement_status: string
  trace_id: string
  trace_status: string
  read_back: true
  sla_business_days: number | null // from the country's source-backed rule; null when no rule covers it
}

/** One turn of the conversation as the API kept it: what the customer wrote and what was rendered for them. `at` is ms since the epoch. */
export type HistoryEntry = { role: 'user'; text: string; at: number } | { role: 'assistant'; reply: Reply; at: number }

/** A handoff of the session, kept by the API apart from the bounded turns. `at` is ms since the epoch. */
export type HistoryCase = { ticketId: string; category: string; at: number }

export type HistoryResult =
  | { ok: true; turns: HistoryEntry[]; cases: HistoryCase[] }
  | { ok: false; failure: 'session_expired' | 'unavailable' }

export type SendFailure =
  | 'session_expired'
  | 'rate_limited'
  | 'unavailable' // never reached the API: safe to send again
  | 'timeout' // may have been processed: the customer decides
  | 'busy' // another send from this session is still in flight
  | 'already_processed' // the API got this message before and no longer keeps its reply
  | 'unexpected'

export type SendResult = { ok: true; reply: Reply } | { ok: false; failure: SendFailure }

export type CaseStatus = { ticket_id: string; status: string; message: string | null }

export type CaseResult =
  | { ok: true; case: CaseStatus }
  | { ok: false; failure: 'session_expired' | 'not_found' | 'unavailable' }

export type DemoScenario = {
  id: string
  path: string
  customer_id: string
  language: string
  fault: string | null
  turns: string[]
  expect: (string | null)[]
  title: { en: string; es: string; pt?: string }
  look_for: { en: string; es: string; pt?: string }
}

export type DemoTicket = {
  ticket_id: string
  queue: string
  priority: string
  category: string
  request: string
  reason: string
  suggested_next_step: string
  open_questions: string[]
  // The codes of the three texts above (agent/policy/notes.py), as the operator console reads them; a ticket filed before them has none.
  reason_code?: { code: string; params?: Record<string, string | number> } | null
  open_question_codes?: ({ code: string; params?: Record<string, string | number> } | null)[]
  next_step_code?: string | null
  created_at: number
}

/** A trace request this session opened, as payments operations receives it (`POST /demo/traces`): what the bank view shows of it. */
export type DemoTrace = {
  trace_id: string
  transaction_id: string
  queue: string
  status: string
  sla_business_days: number | null // null: no source-backed rule, never shown as 0
  created_at: number
}

export type DemoFault = 'expire_session' | 'llm_outage' | 'llm_restore'
