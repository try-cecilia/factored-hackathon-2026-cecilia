import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useI18n, useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import { loadTrace } from '../../server/operator.functions'
import { IconButton, StatusIndicator, type StatusTone } from '../../ui'
import { CloseIcon } from '../../ui/table/icons'
import { categoryName, dispositionName, ms, usd, when } from '../-operator/format'
import { attemptOutcomeName, attemptReasonName, errorTypeName, ruleName } from '../-operator/notes'
import { isAutomatic } from '../-operator/refresh'
import { DataTable } from '../../ui'
import { KeyValues, Notice, Stat } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/trazas/$traceId')({
  loader: ({ params }) => loadTrace({ data: { trace_id: params.traceId, auto: isAutomatic() } }),
  head: ({ matches }) => headTitle(matches, 'operator.pageTitle.trace'),
  component: TracePage,
})

type Attempt = { provider?: string; outcome?: string; reason?: string }
type Step = { step?: number; outcome?: string; attempts?: Attempt[] }
const tones: Record<string, StatusTone> = { AUTO_RESOLVE: 'success', ESCALATE: 'info', CLARIFY: 'neutral', ABSTAIN: 'neutral' }

function TracePage() {
  const t = useT()
  const { locale } = useI18n()
  const navigate = useNavigate()
  const result = Route.useLoaderData()
  if (!result.ok) {
    return (
      <div className="op-ticket-empty">
        {result.status === 404 ? <Notice status={404}>{t('monitor.traces.notFound')}</Notice> : <Notice status={result.status} />}
      </div>
    )
  }
  const trace = result.data
  return (
    <>
      <p className="op-back"><Link to="/operador/trazas">← {t('monitor.traces.back')}</Link></p>
      <article className="op-ticket" aria-labelledby="op-trace-title">
        <header className="op-ticket__head">
          <div className="op-ticket__id">
            <h1 id="op-trace-title" className="op-mono">{trace.trace_id.slice(0, 8)}</h1>
            <StatusIndicator tone={tones[trace.disposition] ?? 'neutral'}>{dispositionName(t, trace.disposition)}</StatusIndicator>
            <span className="op-head__spacer" />
            <IconButton variant="ghost" size="xs" label={t('operator.ticket.close')} icon={<CloseIcon size={12} />} onClick={() => void navigate({ to: '/operador/trazas' })} />
          </div>
          <p className="op-ticket__state op-muted">
            {categoryName(t, trace.category)} · {when(trace.ts, locale)} · <span className="op-mono">{t('monitor.traces.traceId', { id: trace.trace_id })}</span>
          </p>
        </header>

        <div className="op-ticket__body">
          <section className="op-block">
            <h2>{t('monitor.traces.decision')}</h2>
            <p>
              {t('monitor.traces.rule')} {ruleName(t, trace.policy_rule)}
              {trace.policy_rule && ruleName(t, trace.policy_rule) !== trace.policy_rule && <> <span className="op-mono op-muted">({trace.policy_rule})</span></>}
            </p>
            <dl className="op-stats">
              <Stat text name={t('monitor.traces.language')} value={trace.language} />
              <Stat text name={t('monitor.traces.segment')} value={trace.segment ?? '—'} />
              <Stat text name={t('monitor.traces.country')} value={trace.country ?? '—'} />
              <Stat text name={t('monitor.traces.cohort')} value={trace.cohort ?? '—'} />
            </dl>
            {trace.intent_reading && (
              <p className="op-muted">
                {t('monitor.traces.intent', {
                  intent: trace.intent_reading.intent,
                  confidence: (trace.intent_reading.p_intent * 100).toFixed(0),
                  escalation: (trace.intent_reading.p_escalation * 100).toFixed(0),
                  threshold: (trace.intent_reading.threshold * 100).toFixed(0),
                })}
              </p>
            )}
            {trace.ticket_id && (
              <p><Link to="/operador/cola/$ticketId" params={{ ticketId: trace.ticket_id }}>{t('monitor.traces.openTicket')}</Link></p>
            )}
          </section>

          <section className="op-block">
            <h2>{t('monitor.traces.model')}</h2>
            <dl className="op-stats">
              <Stat text name={t('monitor.traces.route')} value={trace.model_route ?? '—'} />
              <Stat text name={t('monitor.traces.modelName')} value={trace.provider ? `${trace.provider}/${trace.model}` : t('monitor.traces.notCalled')} />
              <Stat name={t('monitor.traces.calls')} value={trace.llm_calls} />
              <Stat name={t('monitor.traces.latency')} value={ms(trace.latency_ms)} />
              <Stat name={t('monitor.traces.cost')} value={usd(trace.cost_usd)} />
            </dl>
            {trace.usage && <KeyValues data={trace.usage} />}
            {(trace.llm_steps as Step[] | undefined)?.map((s, i) => (
              <div key={i}>
                <h3>{t('monitor.traces.step', { n: s.step ?? i, outcome: attemptOutcomeName(t, s.outcome) })}</h3>
                <ul className="op-plain">
                  {(s.attempts ?? []).map((a, j) => (
                    <li key={j}><span className="op-mono">{a.provider}</span> · {attemptOutcomeName(t, a.outcome)}{a.reason ? ` (${attemptReasonName(t, a.reason)})` : ''}</li>
                  ))}
                </ul>
              </div>
            ))}
          </section>

          <section className="op-block">
            <div className="op-block__head">
              <h2>{t('monitor.traces.tools')}</h2>
            </div>
            <p className="op-muted">{t('monitor.traces.toolsNote')}</p>
            {(trace.tool_audit ?? []).length === 0 ? (
              <p className="op-muted">{t('monitor.traces.noTools')}</p>
            ) : (
              <DataTable
                density="compact"
                caption={t('monitor.traces.toolsCaption')}
                rows={trace.tool_audit!.map((a, i) => ({ ...a, key: i }))}
                getRowId={(a) => String(a.key)}
                columns={[
                  { id: 'tool', header: t('monitor.traces.tool'), mono: true, rowHeader: true, truncate: true, cell: (a) => a.tool_name },
                  { id: 'outcome', header: t('monitor.traces.outcome'), width: 184, truncate: true, cell: (a) => (a.success ? t('monitor.traces.toolOk') : a.error_type ? <span title={a.error_type}>{errorTypeName(t, a.error_type)}</span> : t('monitor.traces.toolFailed')) },
                  { id: 'duration', header: t('monitor.traces.duration'), width: 76, align: 'end', mono: true, cell: (a) => ms(a.duration_ms) },
                ]}
              />
            )}
          </section>
        </div>
      </article>
    </>
  )
}
