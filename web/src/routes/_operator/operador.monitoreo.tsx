import { createFileRoute, Link, useRouter } from '@tanstack/react-router'
import { useEffect } from 'react'
import { loadMonitor } from '../../server/operator.functions'
import { ago, ms, usd, when } from '../-operator/format'
import { Bars, Loaded, Stat } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/monitoreo')({
  loader: () => loadMonitor(),
  head: () => ({ meta: [{ title: 'Monitoreo · Cecilai' }] }),
  component: Monitor,
})

const pct = (n: number | null | undefined) => (n == null ? '—' : `${(n * 100).toFixed(1)}%`)
const driftLabel: Record<string, string> = {
  stable: 'Estable',
  moderate: 'Moderado',
  significant: 'Significativo',
  insufficient_data: 'Datos insuficientes',
  no_baseline: 'Sin referencia',
}

function Monitor() {
  const m = Route.useLoaderData()
  const router = useRouter()

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') router.invalidate()
    }, 60_000)
    return () => clearInterval(timer)
  }, [router])

  return (
    <div className="op-page">
      <div className="op-pane-head">
        <div>
          <h1>Monitoreo</h1>
          <p className="op-muted">Solo lectura. Sale de los últimos turnos registrados; nada de esto cambia el sistema.</p>
        </div>
        <button type="button" className="op-link" onClick={() => router.invalidate()}>Actualizar</button>
      </div>

      <div className="op-grid">
        <Loaded title="Tráfico" note={m.ops.ok && m.ops.data.from_ts ? `${m.ops.data.turns} turnos · desde ${ago(m.ops.data.from_ts)}` : undefined} result={m.ops}>
          {(o) =>
            o.turns === 0 ? (
              <p className="op-muted">Todavía no hubo turnos registrados.</p>
            ) : (
              <>
                <dl className="op-stats">
                  <Stat name="Latencia p50" value={ms(o.latency_ms_p50)} />
                  <Stat name="Latencia p95" value={ms(o.latency_ms_p95)} />
                  <Stat name="Llamadas al modelo" value={o.llm_calls} />
                  <Stat name="Costo" value={usd(o.cost_usd)} hint={o.unpriced_turns ? `${o.unpriced_turns} turnos sin precio` : undefined} />
                  <Stat name="Modo degradado" value={o.degraded_turns} hint={`${o.llm_unavailable} por modelo caído`} />
                  <Stat name="Rastreos abiertos" value={o.traces_opened} hint={o.handoff_unverified ? `${o.handoff_unverified} traspasos sin confirmar` : undefined} />
                </dl>
                <h3>Resultado de los turnos</h3>
                <Bars data={o.dispositions} total={o.turns} />
                <h3>Derivaciones por categoría</h3>
                <Bars data={o.escalations_by_category} />
                <h3>Reglas más frecuentes</h3>
                <Bars data={o.top_rules} />
                {Object.keys(o.models).length > 0 && (
                  <>
                    <h3>Modelos usados</h3>
                    <Bars data={o.models} />
                  </>
                )}
              </>
            )
          }
        </Loaded>

        <div className="op-stack">
          <Loaded title="Presupuesto del modelo" note="Gasto de hoy (UTC)" result={m.budget}>
            {(b) => (
              <>
                <dl className="op-stats">
                  <Stat name="Gastado hoy" value={usd(b.spent_today_usd)} />
                  <Stat name="Tope diario" value={b.limit_usd ? usd(b.limit_usd, 2) : 'Sin tope'} />
                </dl>
                {b.limit_usd ? (
                  <div className="op-meter" role="meter" aria-label="Presupuesto usado hoy" aria-valuemin={0} aria-valuemax={b.limit_usd} aria-valuenow={Math.min(b.spent_today_usd, b.limit_usd)}>
                    <span style={{ width: `${Math.min(100, (b.spent_today_usd / b.limit_usd) * 100)}%` }} />
                  </div>
                ) : null}
                <p className={b.exhausted ? 'op-error' : 'op-muted'}>
                  {b.exhausted ? 'Tope agotado: el asistente funciona como si el modelo estuviera caído.' : 'Dentro del tope.'}
                </p>
              </>
            )}
          </Loaded>

          <Loaded title="Calidad de datos" result={m.quality}>
            {(q) => (
              <>
                <dl className="op-stats">
                  <Stat name="Última corrida" value={q.summary?.status ?? '—'} hint={q.run_id ? `${q.run_id.slice(0, 12)}` : undefined} />
                  <Stat name="Verificaciones" value={q.summary?.checks_run ?? '—'} />
                  <Stat name="Errores" value={q.summary?.errors_failed ?? '—'} />
                  <Stat name="Advertencias" value={q.summary?.warnings_failed ?? '—'} />
                </dl>
                {q.failed_checks.length === 0 ? (
                  <p className="op-muted">Ninguna verificación falló.</p>
                ) : (
                  <div className="op-table-wrap">
                    <table className="op-table">
                      <caption className="op-sr">Verificaciones que fallaron</caption>
                      <thead><tr><th scope="col">Tabla</th><th scope="col">Verificación</th><th scope="col">Nivel</th><th scope="col" className="op-num">Falló</th></tr></thead>
                      <tbody>
                        {q.failed_checks.slice(0, 12).map((c) => (
                          <tr key={`${c.table}-${c.check}`}>
                            <th scope="row">{c.table}</th>
                            <td className="op-mono">{c.check}</td>
                            <td>{c.severity === 'error' ? 'Error' : 'Advertencia'}</td>
                            <td className="op-num">{pct(c.rate)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {q.failed_checks.length > 12 && <p className="op-muted">Y {q.failed_checks.length - 12} más.</p>}
                  </div>
                )}
              </>
            )}
          </Loaded>
        </div>

        <Loaded title="Drift del tráfico" note="Contra la foto de referencia (PSI)" result={m.drift}>
          {(d) =>
            !d.signals ? (
              <p className="op-muted">
                {d.status === 'no_baseline'
                  ? 'Todavía no hay una referencia. Se toma con POST /admin/drift/snapshot cuando el tráfico luzca normal.'
                  : `${driftLabel[d.status] ?? d.status}: hay ${d.recent_n ?? 0} turnos recientes y ${d.baseline_n ?? 0} en la referencia; hacen falta al menos ${d.min_n ?? 50} de cada lado.`}
              </p>
            ) : (
              <>
                <p><span className={`op-status op-drift-${d.status}`}>{driftLabel[d.status] ?? d.status}</span> <span className="op-muted">{d.recent_n} turnos recientes vs {d.baseline_n}</span></p>
                <div className="op-table-wrap">
                  <table className="op-table">
                    <caption className="op-sr">PSI por señal</caption>
                    <thead><tr><th scope="col">Señal</th><th scope="col" className="op-num">PSI</th><th scope="col">Estado</th></tr></thead>
                    <tbody>
                      {Object.entries(d.signals).map(([name, s]) => (
                        <tr key={name}><th scope="row">{name}</th><td className="op-num">{s.psi.toFixed(3)}</td><td><span className={`op-status op-drift-${s.status}`}>{driftLabel[s.status] ?? s.status}</span></td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )
          }
        </Loaded>

        <Loaded title="Experimentos" note="Shadow y canary" result={m.experiments}>
          {(e) => (
            <>
              <p>
                <span className={`op-chip ${e.config.shadow_enabled ? 'op-chip-on' : ''}`}>Shadow {e.config.shadow_enabled ? 'activo' : 'apagado'}</span>{' '}
                <span className={`op-chip ${e.config.canary_enabled ? 'op-chip-on' : ''}`}>Canary {e.config.canary_enabled ? `activo (${e.config.canary_percent}%)` : 'apagado'}</span>
              </p>
              {e.shadow.turns > 0 ? (
                <dl className="op-stats">
                  <Stat name="Turnos en shadow" value={e.shadow.turns} hint={e.shadow.candidate_errors ? `${e.shadow.candidate_errors} con error del candidato` : undefined} />
                  <Stat name="Mismas herramientas" value={pct(e.shadow.same_tools_rate)} />
                  <Stat name="Mismos argumentos" value={pct(e.shadow.same_args_rate)} />
                  <Stat name="Latencia p50" value={`${ms(e.shadow.latency_ms_p50.primary)} / ${ms(e.shadow.latency_ms_p50.candidate)}`} hint="principal / candidato" />
                </dl>
              ) : (
                <p className="op-muted">Sin turnos en shadow.</p>
              )}
              {e.shadow.turns > 0 && <p className="op-muted">{e.shadow.note}</p>}
              {e.shadow.disagreements.length > 0 && (
                <p className="op-muted">
                  Desacuerdos:{' '}
                  {e.shadow.disagreements.map((x) => (
                    <Link key={x.trace_id} to="/operador/trazas/$traceId" params={{ traceId: x.trace_id }} className="op-mono">{x.trace_id.slice(0, 8)} </Link>
                  ))}
                </p>
              )}
              <h3>Resultados por grupo</h3>
              {Object.keys(e.cohorts).length === 0 ? (
                <p className="op-muted">Sin turnos.</p>
              ) : (
                <div className="op-table-wrap">
                  <table className="op-table">
                    <caption className="op-sr">Resultados por grupo asignado</caption>
                    <thead><tr><th scope="col">Grupo</th><th scope="col" className="op-num">Turnos</th><th scope="col" className="op-num">Derivación</th><th scope="col" className="op-num">Resolución</th><th scope="col" className="op-num">p50</th><th scope="col" className="op-num">Costo</th></tr></thead>
                    <tbody>
                      {Object.entries(e.cohorts).map(([name, c]) => (
                        <tr key={name}><th scope="row">{name}</th><td className="op-num">{c.turns}</td><td className="op-num">{pct(c.escalation_rate)}</td><td className="op-num">{pct(c.auto_resolve_rate)}</td><td className="op-num">{ms(c.latency_ms_p50)}</td><td className="op-num">{usd(c.cost_usd)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </Loaded>
      </div>
      <p className="op-muted op-foot">Actualizado {when(Date.now() / 1000)}.</p>
    </div>
  )
}
