import { createFileRoute, getRouteApi, Link, Outlet, useNavigate, useParams, useRouter } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useI18n, useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import type { Locale } from '../../i18n/locales'
import type { MessageKey, Translate } from '../../i18n/translate'
import type { DeskStatus, QueueRow } from '../../server/operator.functions'
import { Button, DataTable, PriorityChip, priorityOf, StatusIndicator, type Column, type SortState, type StatusTone } from '../../ui'
import { AgeCell } from '../-operator/AgeCell'
import { categoryName, statusKey } from '../-operator/format'
import { useMinute } from '../-operator/now'
import {
  countryOptions, distinct, filterTickets, filtersOf, hasFilters, inScope, isClosed, orderTickets, pageSlice, tabCounts, validateSearch, type QueueSearch, type StatusTab,
} from '../-operator/queue'
import { isOverdue } from '../-operator/sla'
import { LocaleCell, Notice } from '../-operator/ui'

const PAGE_SIZE = 25

export const Route = createFileRoute('/_operator/operador/cola')({
  validateSearch,
  head: ({ matches }) => headTitle(matches, 'operator.pageTitle.queue'),
  component: Queue,
})

const layout = getRouteApi('/_operator')

const tones: Record<DeskStatus, StatusTone> = {
  open: 'open',
  claimed: 'info',
  approved: 'success',
  rejected: 'danger',
  handed_back: 'neutral',
  stale: 'caution',
  resolved: 'success',
}

const TABS: { key: StatusTab; search: QueueSearch['estado']; label: MessageKey }[] = [
  { key: 'all', search: undefined, label: 'operator.queue.tabs.all' },
  { key: 'open', search: 'abiertos', label: 'operator.queue.tabs.open' },
  { key: 'claimed', search: 'tomados', label: 'operator.queue.tabs.claimed' },
  { key: 'decided', search: 'decididos', label: 'operator.queue.tabs.decided' },
]
const PRIORITIES = ['Critical', 'High', 'Medium', 'Low'] as const
const NO_ROWS: QueueRow[] = []
const rowId = (r: QueueRow) => r.ticket_id

function makeColumns(t: Translate, locale: Locale, now: number): Column<QueueRow>[] {
  return [
    { id: 'priority', header: t('operator.queue.columns.priority'), width: 88, sortable: true, cell: (r) => <PriorityChip priority={priorityOf(r.priority)} /> },
    { id: 'ticket', header: t('operator.queue.columns.ticket'), width: 76, mono: true, rowHeader: true, sortable: true, cell: (r) => r.ticket_id.slice(0, 8) },
    { id: 'queue', header: t('operator.queue.columns.queue'), width: 132, mono: true, muted: true, truncate: true, sortable: true, cell: (r) => r.queue },
    { id: 'request', header: t('operator.queue.columns.request'), truncate: true, sortable: true, cell: (r) => <span title={categoryName(t, r.category)}>{r.request}</span> },
    { id: 'locale', header: t('operator.queue.columns.locale'), width: 64, mono: true, muted: true, sortable: true, cell: (r) => <LocaleCell row={r} /> },
    { id: 'age', header: t('operator.queue.columns.age'), width: 64, align: 'end', mono: true, muted: true, sortable: true, cell: (r) => <AgeCell row={r} now={now} locale={locale} /> },
    { id: 'status', header: t('operator.queue.columns.status'), width: 108, sortable: true, cell: (r) => <StatusIndicator tone={tones[r.desk.status]}>{t(statusKey[r.desk.status])}</StatusIndicator> },
    { id: 'operator', header: t('operator.queue.columns.operator'), width: 92, mono: true, truncate: true, sortable: true, cell: (r) => r.desk.operator ?? '—' },
  ]
}

function Queue() {
  const t = useT()
  const { locale } = useI18n()
  // A refresh that brings the same queue keeps the same objects, so the rows that did not change are not drawn again (DataTable).
  const result = layout.useLoaderData({ structuralSharing: true })
  const { view } = Route.useRouteContext()
  const search = Route.useSearch()
  const navigate = useNavigate()
  const router = useRouter()
  const { ticketId } = useParams({ strict: false }) as { ticketId?: string }
  const searchBox = useRef<HTMLInputElement>(null)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<SortState>(null)

  // Ctrl or Cmd+K jumps to the search box, as the hint in it says.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchBox.current?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const now = useMinute()
  const tickets = result.ok ? result.data : NO_ROWS
  const filters = filtersOf(search, q)
  const me = view.operator
  const scope = useMemo(() => inScope(tickets, filters, me, now), [tickets, filters.view, filters.queue, filters.priority, filters.country, filters.language, filters.q, filters.overdue, me, now]) // eslint-disable-line react-hooks/exhaustive-deps
  const counts = tabCounts(scope)
  // How many the button would show: the scope without its own filter, so it does not read 0 while it is on.
  const overdueCount = useMemo(() => inScope(tickets, { ...filters, overdue: false }, me, now).filter((row) => isOverdue(row, now)).length, [tickets, filters.view, filters.queue, filters.priority, filters.country, filters.language, filters.q, me, now]) // eslint-disable-line react-hooks/exhaustive-deps
  const rows = useMemo(() => orderTickets(filterTickets(scope, filters, me, now), sort), [scope, filters.tab, sort, me, now]) // eslint-disable-line react-hooks/exhaustive-deps
  const pending = scope.filter((ticket) => !isClosed(ticket)).length
  const countries = useMemo(() => countryOptions(tickets), [tickets])
  const languages = useMemo(() => distinct(tickets, (ticket) => ticket.language), [tickets])

  // Any change of what is being looked at goes back to the first page.
  const scopeKey = JSON.stringify([filters, sort])
  const [paged, setPaged] = useState({ key: scopeKey, page: 1 })
  const page = paged.key === scopeKey ? paged.page : 1
  const shown = useMemo(() => pageSlice(rows, page, PAGE_SIZE), [rows, page])

  const set = (patch: Partial<QueueSearch>) => void navigate({ search: (prev: QueueSearch) => ({ ...prev, ...patch }) as never, replace: true })
  const clear = () => {
    setQ('')
    void navigate({ search: {} as never, replace: true })
  }

  const title = search.cola ?? t(search.vista === 'mias' ? 'operator.queue.title.mine' : search.vista === 'sin-asignar' ? 'operator.queue.title.unassigned' : 'operator.queue.title.all')

  const columns = useMemo(() => makeColumns(t, locale, now), [t, locale, now])
  const openTicket = useCallback(
    (r: QueueRow) => void navigate({ to: '/operador/cola/$ticketId', params: { ticketId: r.ticket_id }, search: ((prev: QueueSearch) => prev) as never }),
    [navigate],
  )

  const orderLabel = sort
    ? t('operator.queue.order.by', { column: `${columns.find((c) => c.id === sort.key)?.header ?? ''} ${t(sort.direction === 'asc' ? 'operator.queue.order.asc' : 'operator.queue.order.desc')}` })
    : t('operator.queue.order.urgent')

  const emptyKey = !hasFilters(filters) ? (tickets.length === 0 ? 'None' : 'Open') : 'Filtered'
  const empty = {
    title: t(`operator.queue.empty.title${emptyKey}` as MessageKey),
    description: t(`operator.queue.empty.description${emptyKey}` as MessageKey),
    action: hasFilters(filters) ? <Button variant="ghost" tinted size="sm" onClick={clear}>{t('operator.queue.filter.clear')}</Button> : undefined,
  }

  return (
    <div className="op-split" data-detail={ticketId ? 'open' : undefined}>
      <section className="op-list" aria-label={t('operator.queue.caption')}>
        <div className="op-head">
          <h1 className={search.cola ? 'op-mono' : undefined}>{title}</h1>
          <span className="op-count" aria-label={String(pending)}>{result.ok ? pending : ''}</span>
          <div className="op-head__spacer" />
          <label className="op-search">
            <svg viewBox="0 0 20 20" width="12" height="12" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.7" /><path d="M13.2 13.2 17 17" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
            <span className="sr-only">{t('operator.queue.search')}</span>
            <input ref={searchBox} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('operator.queue.searchPlaceholder')} autoComplete="off" spellCheck={false} />
            <kbd aria-hidden="true">{t('operator.queue.searchHint')}</kbd>
          </label>
          <Button variant="ghost" size="sm" onClick={() => router.invalidate()}>{t('operator.refresh')}</Button>
        </div>

        {!result.ok ? (
          <Notice status={result.status} />
        ) : (
          <>
            <div className="op-filters" role="group" aria-label={t('operator.queue.filters')}>
              <div className="op-seg">
                {TABS.map((tab) => (
                  <Link key={tab.key} to="." search={((prev: QueueSearch) => ({ ...prev, estado: tab.search })) as never} replace aria-current={filters.tab === tab.key ? 'true' : undefined}>
                    {t(tab.label)}
                    <span className="op-mono">{counts[tab.key]}</span>
                  </Link>
                ))}
              </div>
              <FilterSelect name={t('operator.queue.filter.priority')} value={search.prioridad} onChange={(v) => set({ prioridad: v })}
                options={PRIORITIES.map((p) => ({ value: p, label: t(`table.priority.${p.toLowerCase() as Lowercase<typeof p>}`) }))} />
              <FilterSelect name={t('operator.queue.filter.country')} value={filters.country} onChange={(v) => set({ pais: v })} options={countries} />
              <FilterSelect name={t('operator.queue.filter.language')} value={search.idioma} onChange={(v) => set({ idioma: v })} options={languages.map((l) => ({ value: l, label: l.toUpperCase() }))} />
              <button type="button" className="op-toggle" aria-pressed={filters.overdue} onClick={() => set({ vencidos: filters.overdue ? undefined : 'si' })}>
                {t('operator.queue.filter.overdue')}
                <span className="op-mono">{overdueCount}</span>
              </button>
              {hasFilters(filters) && <Button variant="ghost" size="xs" onClick={clear}>{t('operator.queue.filter.clear')}</Button>}
              <div className="op-head__spacer" />
              <span className="op-order" aria-live="polite">{orderLabel}</span>
            </div>
            <DataTable
              className="op-table"
              density="compact"
              caption={t('operator.queue.caption')}
              rows={shown.rows}
              columns={columns}
              getRowId={rowId}
              sort={sort}
              onSortChange={setSort}
              onRowClick={openTicket}
              activeRowId={ticketId}
              empty={empty}
              pagination={{ page: shown.page, pageSize: PAGE_SIZE, total: rows.length, onPageChange: (next) => setPaged({ key: scopeKey, page: next }) }}
            />
          </>
        )}
      </section>
      <aside className="op-detail" aria-label={t('operator.ticket.panelLabel')}>
        <Outlet />
      </aside>
    </div>
  )
}

/** A filter that looks like the pills of the design and is a native select underneath: keyboard and screen readers get it for free. */
function FilterSelect({ name, value, onChange, options }: { name: string; value: string | undefined; onChange: (value: string | undefined) => void; options: { value: string; label: string }[] }) {
  return (
    <label className="op-select" data-set={value ? '' : undefined}>
      <select aria-label={name} value={value ?? ''} onChange={(e) => onChange(e.target.value || undefined)}>
        <option value="">{name}</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <svg viewBox="0 0 20 20" width="10" height="10" aria-hidden="true" focusable="false"><path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </label>
  )
}
