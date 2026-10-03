import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import { useMemo } from 'react'
import type { DemoTrace } from '../../chat/types'
import { useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import type { Translate } from '../../i18n/translate'
import { DataTable, type Column } from '../../ui'

export const Route = createFileRoute('/_demobanco/demo/banco_/rastreos')({
  head: ({ matches }) => headTitle(matches, 'demoMode.desk.pageTitle.traces'),
  component: DemoTraces,
})

const layout = getRouteApi('/_demobanco')

function makeColumns(t: Translate): Column<DemoTrace>[] {
  return [
    { id: 'trace', header: t('demoMode.desk.traces.columns.trace'), width: 140, mono: true, rowHeader: true, cell: (r) => r.trace_id },
    { id: 'movement', header: t('demoMode.desk.traces.columns.movement'), mono: true, truncate: true, cell: (r) => r.transaction_id || '—' },
    { id: 'status', header: t('demoMode.desk.traces.columns.status'), width: 120, cell: (r) => r.status || '—' },
    { id: 'sla', header: t('demoMode.desk.traces.columns.sla'), width: 132, muted: true, cell: (r) => (r.sla_business_days ? t('demoMode.desk.traces.sla', { days: r.sla_business_days }) : '—') },
  ]
}

/** "Rastreos": the trace requests this visitor's session opened in the sandbox's tracing service (the bank's side of a trace). */
function DemoTraces() {
  const t = useT()
  const { traces } = layout.useLoaderData({ structuralSharing: true })
  const columns = useMemo(() => makeColumns(t), [t])
  return (
    <section className="op-page demo-traces" aria-label={t('demoMode.desk.traces.caption')}>
      <div className="op-head">
        <h1>{t('demoMode.desk.traces.title')}</h1>
        <span className="op-count">{traces.length}</span>
      </div>
      <DataTable
        className="op-table"
        density="compact"
        caption={t('demoMode.desk.traces.caption')}
        rows={traces}
        columns={columns}
        getRowId={(r) => r.trace_id}
        empty={{ title: t('demoMode.desk.traces.empty') }}
      />
    </section>
  )
}
