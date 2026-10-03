// What the console keeps of the API's customer context (GET /admin/tickets/{id}/customer_context). The API already sends the minimum;
// this is the second lock: a fixed set of fields, so a field the API adds one day does not reach the browser by accident, and an
// account number cannot travel, whatever the API says, because a product's mark is kept only when it is at most four characters.

export type ContextProduct = { product_id: string; type: string; currency: string | null; status: string | null; last4: string | null }
export type ContextMovement = {
  transaction_id: string
  date: string | null
  product_id: string | null
  type: string | null
  amount: number | null
  currency: string | null
  merchant: string | null
  status: string | null
  pending: boolean
}
export type ContextCase = { ticket_id: string; category: string | null; queue: string | null; priority: string | null; created_at: number | null; status: string | null }
export type ContextTrace = { trace_id: string; transaction_id: string | null; status: string | null; created_at: number | null }
export type WarehouseFreshness = 'current' | 'stale' | 'missing' | 'unavailable'

export type CustomerContext = {
  /** The warehouse's own part (products and movements); the cases and traces come from files and are there without it. */
  warehouse: { available: boolean; source: 'account_warehouse'; as_of: string | null; queried_at: string | null; freshness: WarehouseFreshness }
  products: ContextProduct[]
  movements: ContextMovement[]
  /** Pending movements the API left out of `movements` (it lists them all up to a cap). */
  pending_omitted: number
  cases: ContextCase[]
  traces: ContextTrace[]
}

const record = (value: unknown): Record<string, unknown> | null => (typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null)
const text = (value: unknown) => (typeof value === 'string' ? value : null)
const num = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? value : null)
const mark = (value: unknown) => (typeof value === 'string' && /^[A-Za-z0-9]{1,4}$/.test(value) ? value : null)

/** The rows of a list that fit, in order; one that does not (or a list that is not one) is left out, and the rest still shows. */
function rows<T>(list: unknown, read: (row: Record<string, unknown>) => T | null): T[] {
  return Array.isArray(list) ? list.flatMap((item) => { const row = record(item); return (row && read(row)) ?? [] }) : []
}

export function toCustomerContext(raw: unknown): CustomerContext | null {
  const body = record(raw)
  const warehouse = record(body?.warehouse)
  if (!body || !warehouse || typeof warehouse.available !== 'boolean') return null
  const freshness = warehouse.freshness
  return {
    warehouse: {
      available: warehouse.available,
      source: 'account_warehouse',
      as_of: text(warehouse.as_of),
      queried_at: text(warehouse.queried_at),
      freshness: freshness === 'current' || freshness === 'stale' || freshness === 'missing' ? freshness : 'unavailable',
    },
    products: rows(body.products, (p) => (typeof p.product_id === 'string' && typeof p.type === 'string' ? { product_id: p.product_id, type: p.type, currency: text(p.currency), status: text(p.status), last4: mark(p.last4) } : null)),
    movements: rows(body.movements, (m) =>
      typeof m.transaction_id === 'string'
        ? { transaction_id: m.transaction_id, date: text(m.date), product_id: text(m.product_id), type: text(m.type), amount: num(m.amount), currency: text(m.currency), merchant: text(m.merchant), status: text(m.status), pending: m.pending === true }
        : null),
    pending_omitted: typeof body.pending_omitted === 'number' && Number.isInteger(body.pending_omitted) && body.pending_omitted > 0 ? body.pending_omitted : 0,
    cases: rows(body.cases, (c) => (typeof c.ticket_id === 'string' ? { ticket_id: c.ticket_id, category: text(c.category), queue: text(c.queue), priority: text(c.priority), created_at: num(c.created_at), status: text(c.status) } : null)),
    traces: rows(body.traces, (t) => (typeof t.trace_id === 'string' ? { trace_id: t.trace_id, transaction_id: text(t.transaction_id), status: text(t.status), created_at: num(t.created_at) } : null)),
  }
}
