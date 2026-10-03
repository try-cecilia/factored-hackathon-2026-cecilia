import { useMemo } from 'react'
import type { DemoTrace } from '../../chat/types'
import { useT } from '../../i18n/context'
import type { Translate } from '../../i18n/translate'
import { DataTable, type Column } from '../../ui'
import { traceStatusName } from '../-operator/context'

function makeColumns(t: Translate): Column<DemoTrace>[] {
  return [
    { id: 'trace', header: t('demoMode.desk.traces.columns.trace'), width: 140, mono: true, rowHeader: true, cell: (r) => r.trace_id },
    { id: 'movement', header: t('demoMode.desk.traces.columns.movement'), mono: true, truncate: true, cell: (r) => r.transaction_id || '—' },
    { id: 'status', header: t('demoMode.desk.traces.columns.status'), width: 120, cell: (r) => traceStatusName(t, r.status) },
    // null is no source-backed deadline; 0 is a deadline of zero days, said as such.
    { id: 'sla', header: t('demoMode.desk.traces.columns.sla'), width: 132, muted: true, cell: (r) => (r.sla_business_days === null
      ? t('demoMode.desk.traces.slaNone')
      : r.sla_business_days === 1 ? t('demoMode.desk.traces.slaOne') : t('demoMode.desk.traces.sla', { days: r.sla_business_days })) },
  ]
}

/** The trace requests of the session as a table, and as cards on a phone. */
export function DemoTracesView({ traces }: { traces: DemoTrace[] }) {
  const t = useT()
  const columns = useMemo(() => makeColumns(t), [t])
  return (
    <section className={traces.length > 0 ? 'op-page demo-traces demo-traces--cards' : 'op-page demo-traces'} aria-label={t('demoMode.desk.traces.caption')}>
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
      {/* The same four fields per trace, for a phone: the CSS shows one presentation or the other, never both. */}
      {traces.length > 0 && (
        <ul className="demo-traces__cards" aria-label={t('demoMode.desk.traces.caption')}>
          {traces.map((r) => (
            <li key={r.trace_id}>
              <dl>
                {columns.map((c) => (
                  <div key={c.id} className="demo-traces__field">
                    <dt>{c.header}</dt>
                    <dd className={c.mono ? 'op-mono' : undefined}>{c.cell(r, 0)}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
