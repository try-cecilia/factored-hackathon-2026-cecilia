import { createServerFn } from '@tanstack/react-start'
import { toCustomerContext, type CustomerContext } from './customer-context'
import { parseDeskAction } from './desk-action'
import { adminRead, operatorAct, type Result } from './operator-api'
import { publicOrigins } from './origin-check'
import { sameOriginOnly } from './same-origin'
import { operatorSessionState, takeFlash } from './operator-session'
import { toQueueRow, type QueueRow } from './queue-row'

export type { CustomerContext, QueueRow, Result }

// `unknown` does not cross the server-function boundary; the JSON the API sends does.
export type Json = string | number | boolean | null | Json[] | { [key: string]: Json }

export type DeskAction = 'claim' | 'approve' | 'reject' | 'release' | 'resolve'
export type DeskStatus = 'open' | 'claimed' | 'approved' | 'rejected' | 'handed_back' | 'stale' | 'resolved'

export type DeskState = {
  ticket_id: string
  status: DeskStatus
  operator: string | null
  trace_id: string | null
  version: number
  history: { action: string; status: string; operator: string; ts: number; detail: Record<string, Json> }[]
  /** What the customer was told when the case was resolved; null otherwise. An older API leaves it out. */
  message?: string | null
}

export type PendingAction = {
  tool: string
  transaction_id: string
  product_id: string
  review_reason?: string
  age_days?: number
  movement?: { transaction_type?: string; amount?: number | string; currency?: string }
}

/** A text for the operator as a stable code with its parameters. */
export type TextCode = { code: string; params?: Record<string, string | number> }

export type Ticket = {
  ticket_id: string
  trace_id: string | null
  created_at: number
  category: string
  // A case that reaches the console without them (an old or incomplete record) must still be drawn: both may be missing.
  priority?: string | null
  queue: string
  customer_id: string
  session_ref: string
  segment: string | null
  country: string | null
  language?: string | null
  request: string
  prior_requests: string[]
  reason: string
  policy_rule: string
  verified_facts: Record<string, Json>[]
  evidence: { type: string; id: string | null; flagged?: boolean; detail: Record<string, Json> }[]
  actions_taken: Record<string, Json>[]
  open_questions: string[]
  suggested_next_step: string
  // The codes of the three texts above (agent/policy/notes.py). A case filed before them has none: the console shows the English text.
  reason_code?: TextCode | null
  open_question_codes?: (TextCode | null)[]
  next_step_code?: string | null
  pending_action: PendingAction | null
  desk: DeskState
}

export type OperatorView =
  | { status: 'active'; operator: string | null; canAct: boolean; flash: string | null }
  | { status: 'expired' } // there was a session and it is gone: idle too long, over its cap, or the server restarted
  | { status: 'anonymous' }

const clean = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

// `auto` marks a call made by the console's own background refresh: it reads, but does not count as the operator being
// there, so an abandoned tab lets its session expire. Clicks, navigation and actions leave it out.
const autoOf = (input: { auto?: boolean } | undefined) => Boolean(input?.auto)

export const getOperatorView = createServerFn({ method: 'GET' })
  .validator(autoOf)
  .handler(async ({ data: auto }): Promise<OperatorView> => {
    const state = operatorSessionState(!auto)
    if (state.status !== 'active') return { status: state.status }
    return { status: 'active', operator: state.session.operator ?? null, canAct: Boolean(state.session.operatorKey), flash: takeFlash() }
  })

/** The one-shot message a form post left for the login page. */
export const getFlash = createServerFn({ method: 'GET' }).handler(async () => takeFlash())

/** The origins the console trusts (configuration, never something from the request), for the notice of a refused origin. */
export const getPublicOrigins = createServerFn({ method: 'GET' }).handler(async () => (publicOrigins(process.env.WEB_PUBLIC_ORIGIN) ?? []).join(', '))

const idOf = (input: unknown, label: string) => {
  const value = clean((input as Record<string, unknown> | null)?.[label])
  if (!/^[A-Za-z0-9_-]{4,64}$/.test(value)) throw new Error(`${label} is not valid`)
  return value
}

// Rows, not tickets: see QueueRow.
export const loadQueue = createServerFn({ method: 'GET' })
  .validator(autoOf)
  .handler(async ({ data: auto }): Promise<Result<QueueRow[]>> => {
    const result = await adminRead<Ticket[]>('/admin/human_queue?limit=200', !auto)
    return result.ok ? { ok: true, data: result.data.map(toQueueRow) } : result
  })

export const loadTicket = createServerFn({ method: 'GET' })
  .validator((input: unknown) => ({ id: idOf(input, 'ticket_id'), auto: autoOf(input as { auto?: boolean } | undefined) }))
  .handler(({ data }) => adminRead<Ticket>(`/admin/tickets/${data.id}`, !data.auto))

// The customer's context is read on its own, after the case: a slow warehouse must never hold the case back, and a failure here is
// this section's alone. 502: the API answered, but not with the contract.
export const loadCustomerContext = createServerFn({ method: 'GET' })
  .validator((input: unknown) => ({ id: idOf(input, 'ticket_id'), auto: autoOf(input as { auto?: boolean } | undefined) }))
  .handler(async ({ data }): Promise<Result<CustomerContext>> => {
    const result = await adminRead<unknown>(`/admin/tickets/${data.id}/customer_context`, !data.auto)
    if (!result.ok) return result
    const context = toCustomerContext(result.data)
    return context ? { ok: true, data: context } : { ok: false, status: 502 }
  })

// `reason` is the internal note of a rejection; `message`, what the customer reads when the case is resolved.
export const actOnTicket = createServerFn({ method: 'POST' })
  .middleware([sameOriginOnly])
  .validator((input: unknown) => ({ ticket_id: idOf(input, 'ticket_id'), ...parseDeskAction(input) }))
  .handler(({ data }) =>
    operatorAct<DeskState>(`/admin/tickets/${data.ticket_id}/${data.action}`, {
      expected_version: data.expected_version,
      reason: data.reason,
      message: data.message,
    }),
  )

export type Ops = {
  turns: number
  from_ts: number | null
  to_ts: number | null
  dispositions: Record<string, number>
  escalations_by_category: Record<string, number>
  top_rules: Record<string, number>
  degraded_turns: number
  llm_unavailable: number
  handoff_unverified: number
  traces_opened: number
  llm_calls: number
  cost_usd: number
  unpriced_turns: number
  latency_ms_p50: number | null
  latency_ms_p95: number | null
  models: Record<string, number>
}
export type Budget = { limit_usd: number | null; spent_today_usd: number; exhausted: boolean }
export type DriftSignal = { psi: number; status: string; baseline: Record<string, number>; recent: Record<string, number> }
export type Drift = {
  status: string
  baseline_n?: number
  recent_n?: number
  min_n?: number
  hint?: string
  signals?: Record<string, DriftSignal>
}
export type Experiments = {
  shadow: {
    turns: number
    candidate_errors: number
    same_tools_rate: number | null
    same_args_rate: number | null
    latency_ms_p50: { primary: number | null; candidate: number | null }
    disagreements: { trace_id: string }[]
    note: string
  }
  cohorts: Record<string, { turns: number; escalation_rate: number; auto_resolve_rate: number; latency_ms_p50: number; cost_usd: number }>
  config: { canary_percent: number; shadow_enabled: boolean; canary_enabled: boolean }
}
export type DataQuality = {
  run_id?: string
  contract_version?: string
  summary?: { status: string; errors_failed: number; warnings_failed: number; checks_run: number }
  tables?: Record<string, { rows_staged: number; rows_quarantined: number; rows_deduplicated: number }>
  contract_deviations?: { table: string; column: string; observed: string; decision: string }[]
  failed_checks: { table: string; check: string; severity: string; failed: number; total: number; rate: number }[]
}

export type Monitor = {
  ops: Result<Ops>
  budget: Result<Budget>
  drift: Result<Drift>
  quality: Result<DataQuality>
  experiments: Result<Experiments>
}

export const loadMonitor = createServerFn({ method: 'GET' })
  .validator(autoOf)
  .handler(async ({ data: auto }): Promise<Monitor> => {
    const touch = !auto
    const [ops, budget, drift, quality, experiments] = await Promise.all([
      adminRead<Ops>('/admin/ops', touch),
      adminRead<Budget>('/admin/llm_budget', touch),
      adminRead<Drift>('/admin/drift', touch),
      adminRead<DataQuality>('/admin/data_quality', touch),
      adminRead<Experiments>('/admin/experiments', touch),
    ])
    return { ops, budget, drift, quality, experiments }
  })

export type TraceRow = {
  trace_id: string
  ts: number
  disposition: string
  category: string
  policy_rule: string
  language: string
  segment: string | null
  country: string | null
  ticket_id: string | null
  provider: string | null
  model: string | null
  llm_calls: number
  latency_ms: number
  cost_usd: number | null
  model_route?: string
}

export type ToolAudit = {
  tool_name: string
  success: boolean | null
  error_type: string | null
  duration_ms: number | null
}

export type TraceDetail = TraceRow & {
  prompt_version?: string
  cohort?: string
  session_ref?: string
  intent_reading?: { intent: string; p_intent: number; p_escalation: number; threshold: number; model_available: boolean } | null
  usage?: Record<string, number>
  verified_tools?: string[]
  llm_steps?: Record<string, Json>[]
  tool_audit?: ToolAudit[]
}

// Only the fields the console shows leave the server: the API's trace also carries the reply text and what the model saw.
const pick = <T extends object, K extends keyof T>(source: T, keys: readonly K[]) =>
  Object.fromEntries(keys.filter((k) => k in source).map((k) => [k, source[k]])) as Pick<T, K>

const ROW_KEYS = ['trace_id', 'ts', 'disposition', 'category', 'policy_rule', 'language', 'segment', 'country', 'ticket_id',
  'provider', 'model', 'llm_calls', 'latency_ms', 'cost_usd', 'model_route'] as const
const DETAIL_KEYS = [...ROW_KEYS, 'prompt_version', 'cohort', 'session_ref', 'intent_reading', 'usage', 'verified_tools'] as const

export const loadTraceLog = createServerFn({ method: 'GET' })
  .validator(autoOf)
  .handler(async ({ data: auto }): Promise<Result<TraceRow[]>> => {
    const result = await adminRead<TraceRow[]>('/admin/trace_log?limit=200', !auto)
    return result.ok ? { ok: true, data: result.data.map((r) => pick(r, ROW_KEYS)).reverse() } : result
  })

export const loadTrace = createServerFn({ method: 'GET' })
  .validator((input: unknown) => ({ id: idOf(input, 'trace_id'), auto: autoOf(input as { auto?: boolean } | undefined) }))
  .handler(async ({ data }): Promise<Result<TraceDetail>> => {
    const result = await adminRead<TraceDetail & { tool_audit?: (ToolAudit & Record<string, Json>)[]; llm_steps?: unknown[] }>(
      `/admin/traces/${data.id}`,
      !data.auto,
    )
    if (!result.ok) return result
    const tools = (result.data.tool_audit ?? []).map((a) => pick(a, ['tool_name', 'success', 'error_type', 'duration_ms'] as const))
    return { ok: true, data: { ...pick(result.data, DETAIL_KEYS), tool_audit: tools, llm_steps: (result.data.llm_steps ?? []) as Record<string, Json>[] } }
  })
