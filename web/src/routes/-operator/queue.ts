import type { Ticket } from '../../server/operator.functions.ts'
import { clampPage } from '../../ui/table/paging.ts'
import { priorityRank } from '../../ui/table/priority.ts'
import { sortRows, type SortState } from '../../ui/table/sort.ts'
import { CLOSED } from './format.ts'

/** The seven queues of the desk, in the order the sidebar lists them. Any other queue that shows up in the data is added after them. */
export const QUEUES = ['fraud_ops', 'priority_care', 'complaints', 'security_review', 'compliance', 'payments_ops', 'account_payments_l2'] as const

export type View = 'all' | 'mine' | 'unassigned'
export type StatusTab = 'all' | 'open' | 'claimed' | 'decided'

export type QueueFilters = {
  view: View
  queue?: string
  tab: StatusTab
  priority?: string
  country?: string
  language?: string
  q?: string
}

/** The URL's part of the filters. `vista`/`cola`/`estado`/`prioridad`/`pais`/`idioma` are the search params of /operador/cola. */
export type QueueSearch = {
  vista?: 'mias' | 'sin-asignar'
  cola?: string
  estado?: 'abiertos' | 'tomados' | 'decididos'
  prioridad?: string
  pais?: string
  idioma?: string
}

const VIEWS = { mias: 'mine', 'sin-asignar': 'unassigned' } as const
const TABS = { abiertos: 'open', tomados: 'claimed', decididos: 'decided' } as const
// Letters of any alphabet: a queue or a country can carry accents ("Perú"), and a link written by hand may use the name.
const short = (value: unknown) => (typeof value === 'string' && /^[\p{L}\p{N}_ .-]{1,40}$/u.test(value) ? value : undefined)

/** Search params come from a URL anyone can edit: keep what is known and drop the rest. Explicit keys, so the router does not merge the raw ones back in. */
export function validateSearch(search: Record<string, unknown>): QueueSearch {
  return {
    vista: search.vista === 'mias' || search.vista === 'sin-asignar' ? search.vista : undefined,
    cola: short(search.cola),
    estado: search.estado === 'abiertos' || search.estado === 'tomados' || search.estado === 'decididos' ? search.estado : undefined,
    prioridad: search.prioridad === 'Critical' || search.prioridad === 'High' || search.prioridad === 'Medium' || search.prioridad === 'Low' ? search.prioridad : undefined,
    pais: short(search.pais),
    idioma: short(search.idioma),
  }
}

export function filtersOf(search: QueueSearch, q: string): QueueFilters {
  return {
    view: search.vista ? VIEWS[search.vista] : 'all',
    queue: search.cola,
    tab: search.estado ? TABS[search.estado] : 'all',
    priority: search.prioridad,
    country: countryCode(search.pais ?? null) ?? undefined,
    language: search.idioma,
    q: q.trim() || undefined,
  }
}

export const isClosed = (t: Ticket) => CLOSED.includes(t.desk.status)
const isMine = (t: Ticket, me: string | null) => me !== null && t.desk.status === 'claimed' && t.desk.operator === me

const inView = (t: Ticket, view: View, me: string | null) =>
  view === 'mine' ? isMine(t, me) : view === 'unassigned' ? t.desk.status === 'open' : true

const matchesSearch = (t: Ticket, q: string) => {
  const needle = q.toLowerCase()
  return [t.ticket_id, t.request, t.queue, t.category, t.desk.operator, t.customer_id].some((field) => field?.toLowerCase().includes(needle))
}

const inTab = (t: Ticket, tab: StatusTab) =>
  tab === 'all' ? true : tab === 'open' ? t.desk.status === 'open' : tab === 'claimed' ? t.desk.status === 'claimed' : isClosed(t)

/** Everything but the status tab: the scope the tab counts are taken from. */
export function inScope(tickets: readonly Ticket[], f: QueueFilters, me: string | null): Ticket[] {
  return tickets.filter(
    (t) =>
      inView(t, f.view, me) &&
      (!f.queue || t.queue === f.queue) &&
      (!f.priority || t.priority === f.priority) &&
      (!f.country || countryCode(t.country) === f.country) &&
      (!f.language || t.language === f.language) &&
      (!f.q || matchesSearch(t, f.q)),
  )
}

export const filterTickets = (tickets: readonly Ticket[], f: QueueFilters, me: string | null) =>
  inScope(tickets, f, me).filter((t) => inTab(t, f.tab))

export type TabCounts = Record<StatusTab, number>

export function tabCounts(scope: readonly Ticket[]): TabCounts {
  return {
    all: scope.length,
    open: scope.filter((t) => inTab(t, 'open')).length,
    claimed: scope.filter((t) => inTab(t, 'claimed')).length,
    decided: scope.filter((t) => inTab(t, 'decided')).length,
  }
}

export type SidebarCounts = { allOpen: number; mine: number; unassigned: number; queues: { name: string; count: number }[] }

/** What the sidebar shows: pending work only (closed tickets are history, not workload). */
export function sidebarCounts(tickets: readonly Ticket[], me: string | null): SidebarCounts {
  const pending = tickets.filter((t) => !isClosed(t))
  const byQueue = new Map<string, number>(QUEUES.map((q) => [q, 0]))
  for (const t of pending) byQueue.set(t.queue, (byQueue.get(t.queue) ?? 0) + 1)
  return {
    allOpen: pending.length,
    mine: pending.filter((t) => isMine(t, me)).length,
    unassigned: pending.filter((t) => t.desk.status === 'open').length,
    queues: [...byQueue].map(([name, count]) => ({ name, count })),
  }
}

/** Pending work first, most urgent first, then the one that has waited longest; closed work last, latest first. */
export function defaultOrder(tickets: readonly Ticket[]): Ticket[] {
  return [...tickets].sort((a, b) => {
    const closed = Number(isClosed(a)) - Number(isClosed(b))
    if (closed) return closed
    if (isClosed(a)) return b.created_at - a.created_at
    return priorityRank(a.priority.toLowerCase()) - priorityRank(b.priority.toLowerCase()) || a.created_at - b.created_at
  })
}

const STATUS_ORDER = ['open', 'claimed', 'approved', 'rejected', 'handed_back', 'stale']

/** Column order chosen in the header. `age` ascending is the youngest first, so its value is the creation time upside down. */
export function orderTickets(tickets: readonly Ticket[], sort: SortState): Ticket[] {
  if (!sort) return defaultOrder(tickets)
  return sortRows(tickets, sort, (t, key) => {
    switch (key) {
      case 'priority':
        return priorityRank(t.priority.toLowerCase())
      case 'ticket':
        return t.ticket_id
      case 'queue':
        return t.queue
      case 'request':
        return t.request
      case 'locale':
        return `${t.country ?? ''}${t.language}`
      case 'age':
        return -t.created_at
      case 'status':
        return STATUS_ORDER.indexOf(t.desk.status)
      case 'operator':
        return t.desk.operator
      default:
        return null
    }
  })
}

const COUNTRY_CODES: Record<string, string> = {
  argentina: 'AR', brasil: 'BR', brazil: 'BR', chile: 'CL', colombia: 'CO', méxico: 'MX', mexico: 'MX', perú: 'PE', peru: 'PE', uruguay: 'UY',
}

/** The API sends the country's name ("México"); the table has room for its code. A country it does not know stays as it came. */
export const countryCode = (country: string | null) => (country ? COUNTRY_CODES[country.toLowerCase()] ?? country : null)

/** Options of the country filter: the code the URL carries, with the name next to it. */
export function countryOptions(tickets: readonly Ticket[]): { value: string; label: string }[] {
  const byCode = new Map<string, string>()
  for (const t of tickets) {
    const code = countryCode(t.country)
    if (code && t.country && !byCode.has(code)) byCode.set(code, code === t.country ? code : `${code} · ${t.country}`)
  }
  return [...byCode].sort(([a], [b]) => a.localeCompare(b)).map(([value, label]) => ({ value, label }))
}

/** The rows of a page, and the page they belong to: one past the end (a refresh left fewer cases) is the last one, for the rows and for the pager. */
export function pageSlice<T>(rows: readonly T[], page: number, pageSize: number): { page: number; rows: T[] } {
  const current = clampPage(page, rows.length, pageSize)
  return { page: current, rows: rows.slice((current - 1) * pageSize, current * pageSize) }
}

export const localeOf = (t: Ticket) => [countryCode(t.country), t.language.toUpperCase()].filter(Boolean).join('·')

export const distinct = (tickets: readonly Ticket[], pick: (t: Ticket) => string | null) =>
  [...new Set(tickets.map(pick).filter((v): v is string => Boolean(v)))].sort()

export const hasFilters = (f: QueueFilters) => Boolean(f.queue || f.priority || f.country || f.language || f.q || f.view !== 'all' || f.tab !== 'all')
