import { createFileRoute, Outlet, useNavigate, useParams, useRouter } from '@tanstack/react-router'
import { useState } from 'react'
import { useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import { loadTraceLog, type TraceRow } from '../../server/operator.functions'
import { Button, DataTable, StatusIndicator, type Column, type SortState, type StatusTone } from '../../ui'
import { ageShort, categoryName, dispositionName, ms, usd, short } from '../-operator/format'
import { isAutomatic } from '../-operator/refresh'
import { pageSlice } from '../-operator/queue'
import { Notice } from '../-operator/ui'
import { sortRows } from '../../ui'

export const Route = createFileRoute('/_operator/operador/trazas')({
  loader: () => loadTraceLog({ data: { auto: isAutomatic() } }),
  head: ({ matches }) => headTitle(matches, 'operator.pageTitle.traces'),
  component: Traces,
})

const PAGE_SIZE = 25
const tones: Record<string, StatusTone> = { AUTO_RESOLVE: 'success', ESCALATE: 'info', CLARIFY: 'neutral', ABSTAIN: 'neutral' }

function Traces() {
  const t = useT()
  const result = Route.useLoaderData()
  const router = useRouter()
  const navigate = useNavigate()
  const { traceId } = useParams({ strict: false }) as { traceId?: string }
  const [sort, setSort] = useState<SortState>(null)
  const [page, setPage] = useState(1)

  const rows: TraceRow[] = result.ok
    ? sortRows(result.data, sort, (r, key) => {
        switch (key) {
          case 'trace': return r.trace_id
          case 'result': return r.disposition
          case 'category': return r.category
          case 'age': return -r.ts
          case 'latency': return r.latency_ms
          case 'cost': return r.cost_usd
          default: return null
        }
      })
    : []

  const shown = pageSlice(rows, page, PAGE_SIZE)

  const columns: Column<TraceRow>[] = [
    { id: 'trace', header: t('monitor.traces.columns.trace'), width: 84, mono: true, rowHeader: true, sortable: true, cell: (r) => short(r.trace_id) },
    { id: 'result', header: t('monitor.traces.columns.result'), width: 116, sortable: true, cell: (r) => <StatusIndicator tone={tones[r.disposition] ?? 'neutral'}>{dispositionName(t, r.disposition)}</StatusIndicator> },
    { id: 'category', header: t('monitor.traces.columns.category'), truncate: true, sortable: true, cell: (r) => categoryName(t, r.category) },
    { id: 'age', header: t('monitor.traces.columns.age'), width: 52, align: 'end', mono: true, muted: true, sortable: true, cell: (r) => ageShort(r.ts) },
    { id: 'latency', header: t('monitor.traces.columns.latency'), width: 76, align: 'end', mono: true, muted: true, sortable: true, cell: (r) => ms(r.latency_ms) },
    { id: 'cost', header: t('monitor.traces.columns.cost'), width: 100, align: 'end', mono: true, muted: true, sortable: true, cell: (r) => usd(r.cost_usd) },
  ]

  return (
    <div className="op-split" data-detail={traceId ? 'open' : undefined}>
      <section className="op-list" aria-label={t('monitor.traces.title')}>
        <div className="op-head">
          <div>
            <h1>{t('monitor.traces.title')}</h1>
            <p className="op-muted">{result.ok ? t('monitor.traces.subtitle', { count: result.data.length }) : t('monitor.traces.loadFailed')}</p>
          </div>
          <div className="op-head__spacer" />
          <Button variant="ghost" size="sm" onClick={() => router.invalidate()}>{t('operator.refresh')}</Button>
        </div>
        {!result.ok ? (
          <Notice status={result.status} />
        ) : (
          <DataTable
            className="op-table"
            density="compact"
            caption={t('monitor.traces.caption')}
            rows={shown.rows}
            columns={columns}
            getRowId={(r) => r.trace_id}
            sort={sort}
            onSortChange={(next) => {
              setSort(next)
              setPage(1)
            }}
            onRowClick={(r) => void navigate({ to: '/operador/trazas/$traceId', params: { traceId: r.trace_id } })}
            activeRowId={traceId}
            empty={{ title: t('monitor.traces.emptyTitle'), description: t('monitor.traces.emptyBody') }}
            pagination={{ page: shown.page, pageSize: PAGE_SIZE, total: rows.length, onPageChange: setPage }}
          />
        )}
      </section>
      <aside className="op-detail" aria-label={t('monitor.traces.title')}>
        <Outlet />
      </aside>
    </div>
  )
}
