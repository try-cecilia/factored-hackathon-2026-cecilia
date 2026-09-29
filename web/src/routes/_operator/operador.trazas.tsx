import { createFileRoute, Link, Outlet, useRouter } from '@tanstack/react-router'
import { loadTraceLog } from '../../server/operator.functions'
import { ago, categoryLabel, dispositionLabel, label, ms, usd } from '../-operator/format'
import { Empty, Notice } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/trazas')({
  loader: () => loadTraceLog(),
  head: () => ({ meta: [{ title: 'Trazas · Cecilai' }] }),
  component: Traces,
})

function Traces() {
  const result = Route.useLoaderData()
  const router = useRouter()
  return (
    <div className="op-split">
      <div className="op-list-pane">
        <div className="op-pane-head">
          <div>
            <h1>Trazas</h1>
            <p className="op-muted">{result.ok ? `Últimos ${result.data.length} turnos, del más reciente al más antiguo` : 'No se pudo cargar'}</p>
          </div>
          <button type="button" className="op-link" onClick={() => router.invalidate()}>Actualizar</button>
        </div>
        {!result.ok ? (
          <Notice status={result.status} />
        ) : result.data.length === 0 ? (
          <Empty title="No hay trazas">Cada turno del asistente deja una traza.</Empty>
        ) : (
          <ul className="op-cases">
            {result.data.map((t) => (
              <li key={t.trace_id}>
                <Link to="/operador/trazas/$traceId" params={{ traceId: t.trace_id }} activeProps={{ 'aria-current': 'true' }}>
                  <span className="op-case-top">
                    <span className={`op-status op-disp-${t.disposition.toLowerCase()}`}>{label(dispositionLabel, t.disposition)}</span>
                    <span className="op-muted">{ago(t.ts)}</span>
                  </span>
                  <span className="op-case-title">{label(categoryLabel, t.category)}</span>
                  <span className="op-case-meta">
                    <span className="op-mono">{t.trace_id.slice(0, 8)}</span>
                    <span>{ms(t.latency_ms)} · {usd(t.cost_usd)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="op-detail-pane">
        <Outlet />
      </div>
    </div>
  )
}
