import { createFileRoute, Link, useRouter } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useI18n, useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import type { MessageKey } from '../../i18n/translate'
import { loadMonitor } from '../../server/operator.functions'
import { Button, DataTable, StatusIndicator, type StatusTone } from '../../ui'
import { ago, categoryName, dispositionName, ms, usd, when } from '../-operator/format'
import { isAutomatic, refreshQuietly } from '../-operator/refresh'
import { Bars, Loaded, Stat } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/monitoreo')({
  loader: () => loadMonitor({ data: { auto: isAutomatic() } }),
  head: ({ matches }) => headTitle(matches, 'operator.pageTitle.monitor'),
  component: Monitor,
})

const pct = (n: number | null | undefined) => (n == null ? '—' : `${(n * 100).toFixed(1)}%`)
const DRIFT_KEYS = ['stable', 'moderate', 'significant', 'insufficient_data', 'no_baseline'] as const
const driftTone: Record<string, StatusTone> = { stable: 'success', moderate: 'caution', significant: 'danger' }

function Monitor() {
  const t = useT()
  const { locale } = useI18n()
  const m = Route.useLoaderData()
  const router = useRouter()

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void refreshQuietly(router)
    }, 60_000)
    return () => clearInterval(timer)
  }, [router])

  const driftName = (status: string) => (DRIFT_KEYS.includes(status as never) ? t(`monitor.drift.status.${status}` as MessageKey) : status)

  return (
    <div className="op-page">
      <div className="op-head">
        <div>
          <h1>{t('monitor.title')}</h1>
          <p className="op-muted">{t('monitor.subtitle')}</p>
        </div>
        <div className="op-head__spacer" />
        <Button variant="ghost" size="sm" onClick={() => router.invalidate()}>{t('operator.refresh')}</Button>
      </div>

      <div className="op-grid">
        <Loaded title={t('monitor.traffic.title')} note={m.ops.ok && m.ops.data.from_ts ? t('monitor.traffic.note', { turns: m.ops.data.turns, since: ago(m.ops.data.from_ts, locale) }) : undefined} result={m.ops}>
          {(o) =>
            o.turns === 0 ? (
              <p className="op-muted">{t('monitor.empty')}</p>
            ) : (
              <>
                <dl className="op-stats">
                  <Stat name={t('monitor.traffic.p50')} value={ms(o.latency_ms_p50)} />
                  <Stat name={t('monitor.traffic.p95')} value={ms(o.latency_ms_p95)} />
                  <Stat name={t('monitor.traffic.llmCalls')} value={o.llm_calls} />
                  <Stat name={t('monitor.traffic.cost')} value={usd(o.cost_usd)} hint={o.unpriced_turns ? t('monitor.traffic.unpriced', { count: o.unpriced_turns }) : undefined} />
                  <Stat name={t('monitor.traffic.degraded')} value={o.degraded_turns} hint={t('monitor.traffic.degradedHint', { count: o.llm_unavailable })} />
                  <Stat name={t('monitor.traffic.traces')} value={o.traces_opened} hint={o.handoff_unverified ? t('monitor.traffic.unverified', { count: o.handoff_unverified }) : undefined} />
                </dl>
                <h3>{t('monitor.traffic.dispositions')}</h3>
                <Bars data={o.dispositions} total={o.turns} names={Object.fromEntries(Object.keys(o.dispositions).map((k) => [k, dispositionName(t, k)]))} />
                <h3>{t('monitor.traffic.escalations')}</h3>
                <Bars data={o.escalations_by_category} names={Object.fromEntries(Object.keys(o.escalations_by_category).map((k) => [k, categoryName(t, k)]))} />
                <h3>{t('monitor.traffic.rules')}</h3>
                <Bars data={o.top_rules} />
                {Object.keys(o.models).length > 0 && (
                  <>
                    <h3>{t('monitor.traffic.models')}</h3>
                    <Bars data={o.models} />
                  </>
                )}
              </>
            )
          }
        </Loaded>

        <div className="op-stack">
          <Loaded title={t('monitor.budget.title')} note={t('monitor.budget.note')} result={m.budget}>
            {(b) => (
              <>
                <dl className="op-stats">
                  <Stat name={t('monitor.budget.spent')} value={usd(b.spent_today_usd)} />
                  <Stat name={t('monitor.budget.limit')} value={b.limit_usd ? usd(b.limit_usd, 2) : t('monitor.budget.noLimit')} />
                </dl>
                {b.limit_usd ? (
                  <div className="op-meter" role="meter" aria-label={t('monitor.budget.meter')} aria-valuemin={0} aria-valuemax={b.limit_usd} aria-valuenow={Math.min(b.spent_today_usd, b.limit_usd)}>
                    <span style={{ width: `${Math.min(100, (b.spent_today_usd / b.limit_usd) * 100)}%` }} />
                  </div>
                ) : null}
                <p className={b.exhausted ? 'op-warn' : 'op-muted'}>{b.exhausted ? t('monitor.budget.exhausted') : t('monitor.budget.within')}</p>
              </>
            )}
          </Loaded>

          <Loaded title={t('monitor.quality.title')} result={m.quality}>
            {(q) => (
              <>
                <dl className="op-stats">
                  <Stat name={t('monitor.quality.lastRun')} value={q.summary?.status ?? '—'} hint={q.run_id ? `${q.run_id.slice(0, 12)}` : undefined} />
                  <Stat name={t('monitor.quality.checks')} value={q.summary?.checks_run ?? '—'} />
                  <Stat name={t('monitor.quality.errors')} value={q.summary?.errors_failed ?? '—'} />
                  <Stat name={t('monitor.quality.warnings')} value={q.summary?.warnings_failed ?? '—'} />
                </dl>
                {q.failed_checks.length === 0 ? (
                  <p className="op-muted">{t('monitor.quality.none')}</p>
                ) : (
                  <>
                    <DataTable
                      density="compact"
                      caption={t('monitor.quality.caption')}
                      rows={q.failed_checks.slice(0, 12)}
                      getRowId={(c) => `${c.table}-${c.check}`}
                      columns={[
                        { id: 'table', header: t('monitor.quality.table'), rowHeader: true, cell: (c) => c.table },
                        { id: 'check', header: t('monitor.quality.check'), mono: true, truncate: true, cell: (c) => c.check },
                        { id: 'level', header: t('monitor.quality.level'), width: 96, cell: (c) => (c.severity === 'error' ? t('monitor.quality.error') : t('monitor.quality.warning')) },
                        { id: 'failed', header: t('monitor.quality.failed'), width: 64, align: 'end', mono: true, cell: (c) => pct(c.rate) },
                      ]}
                    />
                    {q.failed_checks.length > 12 && <p className="op-muted op-more">{t('monitor.quality.more', { count: q.failed_checks.length - 12 })}</p>}
                  </>
                )}
              </>
            )}
          </Loaded>
        </div>

        <Loaded title={t('monitor.drift.title')} note={t('monitor.drift.note')} result={m.drift}>
          {(d) =>
            !d.signals ? (
              <p className="op-muted">
                {d.status === 'no_baseline'
                  ? t('monitor.drift.noBaseline')
                  : t('monitor.drift.insufficient', { status: driftName(d.status), recent: d.recent_n ?? 0, baseline: d.baseline_n ?? 0, min: d.min_n ?? 50 })}
              </p>
            ) : (
              <>
                <p className="op-drift-summary">
                  <StatusIndicator tone={driftTone[d.status] ?? 'neutral'}>{driftName(d.status)}</StatusIndicator>
                  <span className="op-muted">{t('monitor.drift.recent', { recent: d.recent_n ?? 0, baseline: d.baseline_n ?? 0 })}</span>
                </p>
                <DataTable
                  density="compact"
                  caption={t('monitor.drift.caption')}
                  rows={Object.entries(d.signals)}
                  getRowId={([name]) => name}
                  columns={[
                    { id: 'signal', header: t('monitor.drift.signal'), rowHeader: true, cell: ([name]) => name },
                    { id: 'psi', header: 'PSI', width: 72, align: 'end', mono: true, cell: ([, s]) => s.psi.toFixed(3) },
                    { id: 'state', header: t('monitor.drift.state'), width: 140, cell: ([, s]) => <StatusIndicator tone={driftTone[s.status] ?? 'neutral'}>{driftName(s.status)}</StatusIndicator> },
                  ]}
                />
              </>
            )
          }
        </Loaded>

        <Loaded title={t('monitor.experiments.title')} note={t('monitor.experiments.note')} result={m.experiments}>
          {(e) => (
            <>
              <p className="op-chips">
                <span className={`op-chip ${e.config.shadow_enabled ? 'op-chip--on' : ''}`}>{t(e.config.shadow_enabled ? 'monitor.experiments.shadowOn' : 'monitor.experiments.shadowOff')}</span>
                <span className={`op-chip ${e.config.canary_enabled ? 'op-chip--on' : ''}`}>{e.config.canary_enabled ? t('monitor.experiments.canaryOn', { percent: e.config.canary_percent }) : t('monitor.experiments.canaryOff')}</span>
              </p>
              {e.shadow.turns > 0 ? (
                <dl className="op-stats">
                  <Stat name={t('monitor.experiments.shadowTurns')} value={e.shadow.turns} hint={e.shadow.candidate_errors ? t('monitor.experiments.candidateErrors', { count: e.shadow.candidate_errors }) : undefined} />
                  <Stat name={t('monitor.experiments.sameTools')} value={pct(e.shadow.same_tools_rate)} />
                  <Stat name={t('monitor.experiments.sameArgs')} value={pct(e.shadow.same_args_rate)} />
                  <Stat name={t('monitor.experiments.latency')} value={`${ms(e.shadow.latency_ms_p50.primary)} / ${ms(e.shadow.latency_ms_p50.candidate)}`} hint={t('monitor.experiments.latencyHint')} />
                </dl>
              ) : (
                <p className="op-muted">{t('monitor.experiments.noShadow')}</p>
              )}
              {e.shadow.turns > 0 && <p className="op-muted">{e.shadow.note}</p>}
              {e.shadow.disagreements.length > 0 && (
                <p className="op-muted">
                  {t('monitor.experiments.disagreements')}{' '}
                  {e.shadow.disagreements.map((x) => (
                    <Link key={x.trace_id} to="/operador/trazas/$traceId" params={{ traceId: x.trace_id }} className="op-mono">{x.trace_id.slice(0, 8)} </Link>
                  ))}
                </p>
              )}
              <h3>{t('monitor.experiments.cohorts')}</h3>
              {Object.keys(e.cohorts).length === 0 ? (
                <p className="op-muted">{t('monitor.experiments.noCohorts')}</p>
              ) : (
                <DataTable
                  density="compact"
                  caption={t('monitor.experiments.cohortCaption')}
                  rows={Object.entries(e.cohorts)}
                  getRowId={([name]) => name}
                  columns={[
                    { id: 'group', header: t('monitor.experiments.group'), rowHeader: true, cell: ([name]) => name },
                    { id: 'turns', header: t('monitor.experiments.turns'), width: 60, align: 'end', mono: true, cell: ([, c]) => c.turns },
                    { id: 'escalation', header: t('monitor.experiments.escalation'), width: 84, align: 'end', mono: true, cell: ([, c]) => pct(c.escalation_rate) },
                    { id: 'resolution', header: t('monitor.experiments.resolution'), width: 84, align: 'end', mono: true, cell: ([, c]) => pct(c.auto_resolve_rate) },
                    { id: 'p50', header: t('monitor.experiments.p50'), width: 60, align: 'end', mono: true, cell: ([, c]) => ms(c.latency_ms_p50) },
                    { id: 'cost', header: t('monitor.experiments.cost'), width: 96, align: 'end', mono: true, cell: ([, c]) => usd(c.cost_usd) },
                  ]}
                />
              )}
            </>
          )}
        </Loaded>
      </div>
      <p className="op-muted op-foot">{t('monitor.updated', { when: when(Date.now() / 1000, locale) })}</p>
    </div>
  )
}
