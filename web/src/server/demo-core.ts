import type { DemoTrace } from '../chat/types'

// What `/demo/traces` returns, without the framework, like history-core.ts: the server function wires it to the session cookie, the
// tests to a list. Only what the bank view shows leaves the server (not the customer, the product or the session).

/** A request that does not fit the contract is left out; the rest of the list still shows. */
export function parseTraces(raw: unknown): DemoTrace[] {
  if (!Array.isArray(raw)) return []
  return raw.flatMap((item): DemoTrace[] => {
    if (typeof item !== 'object' || item === null) return []
    const t = item as Record<string, unknown>
    if (typeof t.trace_id !== 'string' || t.trace_id === '') return []
    return [{
      trace_id: t.trace_id,
      transaction_id: typeof t.transaction_id === 'string' ? t.transaction_id : '',
      queue: typeof t.queue === 'string' ? t.queue : '',
      status: typeof t.status === 'string' ? t.status : '',
      sla_business_days: typeof t.sla_business_days === 'number' && Number.isFinite(t.sla_business_days) ? t.sla_business_days : 0,
      created_at: typeof t.created_at === 'number' && Number.isFinite(t.created_at) ? t.created_at : 0,
    }]
  })
}
