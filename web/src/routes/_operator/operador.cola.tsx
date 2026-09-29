import { createFileRoute, Link, Outlet, useRouter } from '@tanstack/react-router'
import { useEffect, useMemo } from 'react'
import { loadQueue, type Ticket } from '../../server/operator.functions'
import { ago, CLOSED, categoryLabel, label, PRIORITY_ORDER, priorityLabel, statusLabel } from '../-operator/format'
import { isAutomatic, refreshQuietly } from '../-operator/refresh'
import { Empty, Notice } from '../-operator/ui'

type Filter = 'abiertos' | 'cerrados' | 'todos'
const FILTERS: { key: Filter; name: string }[] = [
  { key: 'abiertos', name: 'Pendientes' },
  { key: 'cerrados', name: 'Cerrados' },
  { key: 'todos', name: 'Todos' },
]
const REFRESH_MS = 30_000

export const Route = createFileRoute('/_operator/operador/cola')({
  validateSearch: (search: Record<string, unknown>): { estado?: Filter } => ({
    estado: search.estado === 'cerrados' || search.estado === 'todos' ? search.estado : undefined,
  }),
  loader: () => loadQueue({ data: { auto: isAutomatic() } }),
  head: () => ({ meta: [{ title: 'Cola · Cecilai' }] }),
  component: Queue,
})

const rank = (t: Ticket) => {
  const i = PRIORITY_ORDER.indexOf(t.priority)
  return i === -1 ? PRIORITY_ORDER.length : i
}

/** Pending work: most urgent first, then the one that has waited longest. Closed work: latest first. */
function arrange(tickets: Ticket[], filter: Filter) {
  const closed = (t: Ticket) => CLOSED.includes(t.desk.status)
  const shown = tickets.filter((t) => (filter === 'todos' ? true : filter === 'cerrados' ? closed(t) : !closed(t)))
  return shown.sort((a, b) =>
    filter === 'cerrados' ? b.created_at - a.created_at : Number(closed(a)) - Number(closed(b)) || rank(a) - rank(b) || a.created_at - b.created_at,
  )
}

function Queue() {
  const result = Route.useLoaderData()
  const { estado = 'abiertos' } = Route.useSearch()
  const router = useRouter()

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void refreshQuietly(router)
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [router])

  const tickets = useMemo(() => (result.ok ? arrange(result.data, estado) : []), [result, estado])
  const pending = result.ok ? result.data.filter((t) => !CLOSED.includes(t.desk.status)).length : 0

  return (
    <div className="op-split">
      <div className="op-list-pane">
        <div className="op-pane-head">
          <div>
            <h1>Cola humana</h1>
            <p className="op-muted">{result.ok ? `${pending} pendiente${pending === 1 ? '' : 's'} de ${result.data.length}` : 'No se pudo cargar'}</p>
          </div>
          <button type="button" className="op-link" onClick={() => router.invalidate()}>Actualizar</button>
        </div>
        <nav className="op-tabs" aria-label="Filtrar casos">
          {FILTERS.map((f) => (
            <Link key={f.key} to="/operador/cola" search={{ estado: f.key === 'abiertos' ? undefined : f.key }} data-on={estado === f.key ? 'true' : undefined}>
              {f.name}
            </Link>
          ))}
        </nav>
        {!result.ok ? (
          <Notice status={result.status} />
        ) : tickets.length === 0 ? (
          <Empty title={estado === 'abiertos' ? 'No hay casos pendientes' : 'No hay casos para mostrar'}>
            {estado === 'abiertos' ? 'Cuando el asistente derive un caso a una persona, aparece acá.' : 'Probá con otro filtro.'}
          </Empty>
        ) : (
          <ul className="op-cases">
            {tickets.map((t) => (
              <li key={t.ticket_id}>
                <Link to="/operador/cola/$ticketId" params={{ ticketId: t.ticket_id }} search={{ estado: estado === 'abiertos' ? undefined : estado }} activeProps={{ 'aria-current': 'true' }}>
                  <span className="op-case-top">
                    <span className={`op-priority op-priority-${t.priority.toLowerCase()}`}>{label(priorityLabel, t.priority)}</span>
                    <span className="op-muted" title={new Date(t.created_at * 1000).toLocaleString('es')}>{ago(t.created_at)}</span>
                  </span>
                  <span className="op-case-title">{label(categoryLabel, t.category)}</span>
                  <span className="op-case-request">{t.request}</span>
                  <span className="op-case-meta">
                    <span className={`op-status op-status-${t.desk.status}`}>{statusLabel[t.desk.status]}{t.desk.status === 'claimed' && t.desk.operator ? ` · ${t.desk.operator}` : ''}</span>
                    <span className="op-mono">{t.queue}</span>
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
