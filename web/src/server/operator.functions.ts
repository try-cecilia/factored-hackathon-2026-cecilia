import { createServerFn } from '@tanstack/react-start'
import { adminRead, operatorAct, type Result } from './operator-api'
import { getOperatorSession, takeFlash } from './operator-session'

export type { Result }

// `unknown` does not cross the server-function boundary; the JSON the API sends does.
export type Json = string | number | boolean | null | Json[] | { [key: string]: Json }

export type DeskAction = 'claim' | 'approve' | 'reject' | 'release'
export type DeskStatus = 'open' | 'claimed' | 'approved' | 'rejected' | 'handed_back' | 'stale'

export type DeskState = {
  ticket_id: string
  status: DeskStatus
  operator: string | null
  trace_id: string | null
  version: number
  history: { action: string; status: string; operator: string; ts: number; detail: Record<string, Json> }[]
}

export type PendingAction = {
  tool: string
  transaction_id: string
  product_id: string
  review_reason?: string
  age_days?: number
  movement?: { transaction_type?: string; amount?: number | string; currency?: string }
}

export type Ticket = {
  ticket_id: string
  trace_id: string | null
  created_at: number
  category: string
  priority: string
  queue: string
  customer_id: string
  session_ref: string
  segment: string | null
  country: string | null
  language: string
  request: string
  prior_requests: string[]
  reason: string
  policy_rule: string
  verified_facts: Record<string, Json>[]
  evidence: { type: string; id: string | null; flagged?: boolean; detail: Record<string, Json> }[]
  actions_taken: Record<string, Json>[]
  open_questions: string[]
  suggested_next_step: string
  pending_action: PendingAction | null
  desk: DeskState
}

export type OperatorView = { operator: string | null; canAct: boolean; flash: string | null }

const clean = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

export const getOperatorView = createServerFn({ method: 'GET' }).handler(async (): Promise<OperatorView | null> => {
  const session = getOperatorSession()
  return session ? { operator: session.operator ?? null, canAct: Boolean(session.operatorKey), flash: takeFlash() } : null
})

/** The one-shot message a form post left for the login page. */
export const getFlash = createServerFn({ method: 'GET' }).handler(async () => takeFlash())

const idOf = (input: unknown, label: string) => {
  const value = clean((input as Record<string, unknown> | null)?.[label])
  if (!/^[A-Za-z0-9_-]{4,64}$/.test(value)) throw new Error(`${label} is not valid`)
  return value
}

export const loadQueue = createServerFn({ method: 'GET' }).handler(() => adminRead<Ticket[]>('/admin/human_queue?limit=200'))

export const loadTicket = createServerFn({ method: 'GET' })
  .validator((input: unknown) => idOf(input, 'ticket_id'))
  .handler(({ data }) => adminRead<Ticket>(`/admin/tickets/${data}`))

export const actOnTicket = createServerFn({ method: 'POST' })
  .validator((input: unknown) => {
    const { action, expected_version, reason } = (input ?? {}) as Record<string, unknown>
    if (!['claim', 'approve', 'reject', 'release'].includes(action as string)) throw new Error('action is not valid')
    if (expected_version !== undefined && !Number.isInteger(expected_version)) throw new Error('expected_version must be an integer')
    const note = clean(reason).slice(0, 300)
    return {
      ticket_id: idOf(input, 'ticket_id'),
      action: action as DeskAction,
      expected_version: expected_version as number | undefined,
      reason: note || undefined,
    }
  })
  .handler(({ data }) =>
    operatorAct<DeskState>(`/admin/tickets/${data.ticket_id}/${data.action}`, {
      expected_version: data.expected_version,
      reason: data.reason,
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

export const loadMonitor = createServerFn({ method: 'GET' }).handler(async (): Promise<Monitor> => {
  const [ops, budget, drift, quality, experiments] = await Promise.all([
    adminRead<Ops>('/admin/ops'),
    adminRead<Budget>('/admin/llm_budget'),
    adminRead<Drift>('/admin/drift'),
    adminRead<DataQuality>('/admin/data_quality'),
    adminRead<Experiments>('/admin/experiments'),
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

export const loadTraceLog = createServerFn({ method: 'GET' }).handler(async (): Promise<Result<TraceRow[]>> => {
  const result = await adminRead<TraceRow[]>('/admin/trace_log?limit=200')
  return result.ok ? { ok: true, data: result.data.map((r) => pick(r, ROW_KEYS)).reverse() } : result
})

export const loadTrace = createServerFn({ method: 'GET' })
  .validator((input: unknown) => idOf(input, 'trace_id'))
  .handler(async ({ data }): Promise<Result<TraceDetail>> => {
    const result = await adminRead<TraceDetail & { tool_audit?: (ToolAudit & Record<string, Json>)[]; llm_steps?: unknown[] }>(
      `/admin/traces/${data}`,
    )
    if (!result.ok) return result
    const tools = (result.data.tool_audit ?? []).map((a) => pick(a, ['tool_name', 'success', 'error_type', 'duration_ms'] as const))
    return { ok: true, data: { ...pick(result.data, DETAIL_KEYS), tool_audit: tools, llm_steps: (result.data.llm_steps ?? []) as Record<string, Json>[] } }
  })
