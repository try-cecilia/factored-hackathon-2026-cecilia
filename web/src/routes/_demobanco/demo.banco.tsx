import { createFileRoute, getRouteApi, Outlet, useNavigate, useParams } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'
import { useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import type { Translate } from '../../i18n/translate'
import type { DeskStatus, QueueRow } from '../../server/operator.functions'
import { DataTable, PriorityChip, priorityOf, StatusIndicator, type Column, type StatusTone } from '../../ui'
import { categoryName, explainKey, statusKey } from '../-operator/format'

export const Route = createFileRoute('/_demobanco/demo/banco')({
  head: ({ matches }) => headTitle(matches, 'demoMode.desk.pageTitle.queue'),
  component: DemoQueue,
})

const layout = getRouteApi('/_demobanco')

const tones: Record<DeskStatus, StatusTone> = { open: 'open', claimed: 'info', approved: 'success', rejected: 'danger', handed_back: 'neutral', stale: 'caution', resolved: 'success' }
const NO_ROWS: QueueRow[] = []
const rowId = (r: QueueRow) => r.ticket_id

function makeColumns(t: Translate): Column<QueueRow>[] {
  return [
    { id: 'priority', header: t('demoMode.desk.queue.columns.priority'), width: 88, cell: (r) => <PriorityChip priority={priorityOf(r.priority)} /> },
    { id: 'ticket', header: t('demoMode.desk.queue.columns.ticket'), width: 92, mono: true, rowHeader: true, cell: (r) => r.ticket_id.slice(0, 8) },
    { id: 'request', header: t('demoMode.desk.queue.columns.request'), truncate: true, cell: (r) => <span title={categoryName(t, r.category)}>{r.request}</span> },
    { id: 'status', header: t('demoMode.desk.queue.columns.status'), width: 108, cell: (r) => <StatusIndicator tone={tones[r.desk.status]}>{t(statusKey[r.desk.status])}</StatusIndicator> },
  ]
}

/** "Tus casos": the cases this visitor's session filed, newest first, with the case of the URL beside them (or over them, on a small screen). */
function DemoQueue() {
  const t = useT()
  const { queue } = layout.useLoaderData({ structuralSharing: true })
  const navigate = useNavigate()
  const { ticketId } = useParams({ strict: false }) as { ticketId?: string }
  const rows = queue?.ok ? queue.data : NO_ROWS
  const columns = useMemo(() => makeColumns(t), [t])
  const open = useCallback((r: QueueRow) => void navigate({ to: '/demo/banco/caso/$ticketId', params: { ticketId: r.ticket_id } }), [navigate])

  return (
    <div className="op-split" data-detail={ticketId ? 'open' : undefined}>
      <section className="op-list demo-queue" aria-label={t('demoMode.desk.queue.caption')}>
        <div className="op-head">
          <h1>{t('demoMode.desk.queue.title')}</h1>
          <span className="op-count">{queue?.ok ? rows.length : ''}</span>
        </div>
        {queue && !queue.ok ? (
          <div className="op-notice" role="alert"><p>{t(explainKey(queue.status))}</p></div>
        ) : (
          <DataTable
            className="op-table op-table--queue"
            density="compact"
            caption={t('demoMode.desk.queue.caption')}
            rows={rows}
            columns={columns}
            getRowId={rowId}
            onRowClick={open}
            activeRowId={ticketId}
            empty={{ title: t('demoMode.desk.queue.emptyTitle'), description: t('demoMode.desk.queue.emptyBody') }}
          />
        )}
        <aside className="demo-help">
          <h2>{t('demoMode.desk.help.title')}</h2>
          <p>{t('demoMode.desk.help.body')}</p>
        </aside>
      </section>
      <aside className="op-detail" aria-label={t('operator.ticket.panelLabel')}>
        <Outlet />
      </aside>
    </div>
  )
}
