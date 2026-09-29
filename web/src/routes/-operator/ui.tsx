import { useRouter } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import type { Result } from '../../server/operator.functions'
import { Button, EmptyState } from '../../ui'
import { explainKey } from './format'

/** The BFF or the API said no: what happened and the one way out (sign in again, or try again). */
export function Notice({ status, acting, children }: { status?: number; acting?: boolean; children?: ReactNode }) {
  const t = useT()
  const router = useRouter()
  const expired = status === 0 || status === 401
  return (
    <div className="op-notice" role="alert">
      <p>{children ?? t(explainKey(status ?? 500, acting))}</p>
      {expired ? (
        <a className="ui-btn ui-btn--ghost ui-btn--tinted ui-btn--sm" href="/operador/login"><span>{t('operator.goToLogin')}</span></a>
      ) : (
        <Button variant="ghost" tinted size="sm" onClick={() => router.invalidate()}>{t('operator.retry')}</Button>
      )}
    </div>
  )
}

export const Empty = ({ title, children }: { title: string; children?: string }) => <EmptyState className="op-empty" title={title} description={children} />

/** A tonal card of the monitoring page: a title, a quiet note and the data. */
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
  const t = useT()
  return (
    <Panel title={title} note={note}>
      {result.ok ? children(result.data) : <Notice status={result.status}>{result.status === 404 ? t('operator.errors.noPanelData') : undefined}</Notice>}
    </Panel>
  )
}

/** A label and its value. Numbers and ids are mono; a word (a language, a route, "no limit") is `text`. */
export const Stat = ({ name, value, hint, text }: { name: string; value: ReactNode; hint?: ReactNode; text?: boolean }) => (
  <div className={text ? 'op-stat op-stat--text' : 'op-stat'}>
    <dt>{name}</dt>
    <dd>{value}</dd>
    {hint && <p>{hint}</p>}
  </div>
)

export function Bars({ data, total, names }: { data: Record<string, number>; total?: number; names?: Record<string, string> }) {
  const t = useT()
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1])
  const max = total ?? Math.max(1, ...rows.map(([, n]) => n))
  if (!rows.length) return <p className="op-muted">{t('operator.noData')}</p>
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

/** `label` writes a key in the operator's language; without it the keys show as they came. */
export function KeyValues({ data, label }: { data: Record<string, unknown>; label?: (key: string) => string }) {
  const t = useT()
  const entries = Object.entries(data)
  if (!entries.length) return <p className="op-muted">{t('operator.noData')}</p>
  return (
    <dl className="op-kv">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{label ? label(key) : key}</dt>
          <dd className={typeof value === 'object' && value !== null ? 'op-mono' : undefined}>{scalar(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Small mono chip for ids and codes next to a label. */
export const Code = ({ children }: { children: ReactNode }) => <span className="op-mono">{children}</span>
