import { useRouter } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import type { Result } from '../../server/operator.functions'
import { explain } from './format'

export function Notice({ status, acting, children }: { status?: number; acting?: boolean; children?: ReactNode }) {
  const router = useRouter()
  const expired = status === 0 || status === 401
  return (
    <div className="op-notice" role="alert">
      <p>{children ?? explain(status ?? 500, acting)}</p>
      {expired ? (
        <a className="op-link" href="/operador/login">Ir al ingreso</a>
      ) : (
        <button type="button" className="op-link" onClick={() => router.invalidate()}>Reintentar</button>
      )}
    </div>
  )
}

export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => (
  <div className="op-empty">
    <p className="op-empty-title">{title}</p>
    {children && <p>{children}</p>}
  </div>
)

export function Panel({ title, note, children }: { title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section className="op-panel" aria-label={title}>
      <header>
        <h2>{title}</h2>
        {note && <p>{note}</p>}
      </header>
      {children}
    </section>
  )
}

/** A panel whose data may have failed on its own: one broken endpoint must not blank the whole page. */
export function Loaded<T>({ title, note, result, children }: {
  title: string
  note?: ReactNode
  result: Result<T>
  children: (data: T) => ReactNode
}) {
  return (
    <Panel title={title} note={note}>
      {result.ok ? children(result.data) : <Notice status={result.status}>{result.status === 404 ? 'Todavía no hay datos para este panel.' : undefined}</Notice>}
    </Panel>
  )
}

export const Stat = ({ name, value, hint }: { name: string; value: ReactNode; hint?: ReactNode }) => (
  <div className="op-stat">
    <dt>{name}</dt>
    <dd>{value}</dd>
    {hint && <p>{hint}</p>}
  </div>
)

export function Bars({ data, total, names }: { data: Record<string, number>; total?: number; names?: Record<string, string> }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1])
  const max = total ?? Math.max(1, ...rows.map(([, n]) => n))
  if (!rows.length) return <p className="op-muted">Sin datos.</p>
  return (
    <ul className="op-bars">
      {rows.map(([name, n]) => (
        <li key={name}>
          <span className="op-bars-name" title={name}>{names?.[name] ?? name}</span>
          <span className="op-bars-track" aria-hidden="true"><span style={{ width: `${Math.max(2, (n / max) * 100)}%` }} /></span>
          <span className="op-bars-n">{n}</span>
        </li>
      ))}
    </ul>
  )
}

const scalar = (value: unknown) =>
  value === null || value === undefined || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)

export function KeyValues({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (!entries.length) return <p className="op-muted">Sin datos.</p>
  return (
    <dl className="op-kv">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd className={typeof value === 'object' && value !== null ? 'op-mono' : undefined}>{scalar(value)}</dd>
        </div>
      ))}
    </dl>
  )
}
