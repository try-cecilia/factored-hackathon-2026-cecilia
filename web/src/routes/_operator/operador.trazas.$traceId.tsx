import { createFileRoute, Link } from '@tanstack/react-router'
import { loadTrace } from '../../server/operator.functions'
import { categoryLabel, dispositionLabel, label, ms, usd, when } from '../-operator/format'
import { KeyValues, Notice, Panel, Stat } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/trazas/$traceId')({
  loader: ({ params }) => loadTrace({ data: { trace_id: params.traceId } }),
  head: () => ({ meta: [{ title: 'Traza · Cecilai' }] }),
  component: TracePage,
})

type Attempt = { provider?: string; outcome?: string; reason?: string }
type Step = { step?: number; outcome?: string; attempts?: Attempt[] }

function TracePage() {
  const result = Route.useLoaderData()
  if (!result.ok) return result.status === 404 ? <Notice status={404}>No encontramos esa traza. Puede haber salido de la ventana de retención.</Notice> : <Notice status={result.status} />
  const t = result.data
  return (
    <article className="op-ticket" aria-labelledby="op-trace-title">
      <header className="op-ticket-head">
        <p className="op-back"><Link to="/operador/trazas">← Volver a las trazas</Link></p>
        <div className="op-ticket-badges">
          <span className={`op-status op-disp-${t.disposition.toLowerCase()}`}>{label(dispositionLabel, t.disposition)}</span>
        </div>
        <h1 id="op-trace-title">{label(categoryLabel, t.category)}</h1>
        <p className="op-muted">{when(t.ts)} · traza <span className="op-mono">{t.trace_id}</span></p>
      </header>

      <Panel title="Decisión">
        <p>Regla aplicada: <span className="op-mono">{t.policy_rule || '—'}</span></p>
        <dl className="op-stats">
          <Stat name="Idioma" value={t.language} />
          <Stat name="Segmento" value={t.segment ?? '—'} />
          <Stat name="País" value={t.country ?? '—'} />
          <Stat name="Cohorte" value={t.cohort ?? '—'} />
        </dl>
        {t.intent_reading && (
          <p className="op-muted">
            Intención leída: <span className="op-mono">{t.intent_reading.intent}</span> (confianza {(t.intent_reading.p_intent * 100).toFixed(0)}%, probabilidad de derivación {(t.intent_reading.p_escalation * 100).toFixed(0)}% contra umbral {(t.intent_reading.threshold * 100).toFixed(0)}%).
          </p>
        )}
        {t.ticket_id && <p><Link to="/operador/cola/$ticketId" params={{ ticketId: t.ticket_id }}>Ver el caso que generó</Link></p>}
      </Panel>

      <Panel title="Modelo">
        <dl className="op-stats">
          <Stat name="Ruta" value={t.model_route ?? '—'} />
          <Stat name="Modelo" value={t.provider ? `${t.provider}/${t.model}` : 'No se llamó'} />
          <Stat name="Llamadas" value={t.llm_calls} />
          <Stat name="Latencia" value={ms(t.latency_ms)} />
          <Stat name="Costo" value={usd(t.cost_usd)} />
        </dl>
        {t.usage && <KeyValues data={t.usage} />}
        {(t.llm_steps as Step[] | undefined)?.map((s, i) => (
          <div key={i}>
            <h3>Paso {s.step ?? i}: {s.outcome ?? '—'}</h3>
            <ul className="op-plain">
              {(s.attempts ?? []).map((a, j) => (
                <li key={j}><span className="op-mono">{a.provider}</span> · {a.outcome}{a.reason ? ` (${a.reason})` : ''}</li>
              ))}
            </ul>
          </div>
        ))}
      </Panel>

      <Panel title="Herramientas" note="Solo nombre, resultado y duración; los argumentos no se muestran.">
        {(t.tool_audit ?? []).length === 0 ? (
          <p className="op-muted">Este turno no llamó herramientas.</p>
        ) : (
          <div className="op-table-wrap">
            <table className="op-table">
              <caption className="op-sr">Llamadas a herramientas del turno</caption>
              <thead><tr><th scope="col">Herramienta</th><th scope="col">Resultado</th><th scope="col" className="op-num">Duración</th></tr></thead>
              <tbody>
                {t.tool_audit!.map((a, i) => (
                  <tr key={i}><th scope="row" className="op-mono">{a.tool_name}</th><td>{a.success ? 'Correcta' : a.error_type ?? 'Falló'}</td><td className="op-num">{ms(a.duration_ms)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </article>
  )
}
