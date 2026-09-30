import { useEffect, useState, type ReactNode } from 'react'
import { useI18n, useT } from '../../i18n/context'
import type { CustomerContext } from '../../server/customer-context'
import type { DeskStatus, Result } from '../../server/operator.functions'
import { Button } from '../../ui'
import { ago, categoryName, explainKey, money, shortStamp, statusKey } from './format'
import { maskOf, movementStatusName, movementTypeName, productStatusName, productTypeName, traceStatusName } from './context'

type Props = {
  ticketId: string
  /** Reads the context of this case. It never throws: a failure is a `{ ok: false }` result (see `guarded`). */
  load: (ticketId: string) => Promise<Result<CustomerContext>>
  /** Wraps the label of another case in the link that opens it. Left out, the id is plain text. */
  caseLink?: (ticketId: string, label: ReactNode) => ReactNode
}

/**
 * The customer beside the case: read-only, and independent of the rest of the panel. It reads on its own once the case is on screen,
 * so a slow or absent warehouse never delays or breaks the case; when it cannot be read it says so and offers to try again.
 */
export function CustomerContextSection({ ticketId, load, caseLink }: Props) {
  const [attempt, setAttempt] = useState(0)
  const key = `${ticketId}:${attempt}`
  const [read, setRead] = useState<{ key: string; result: Result<CustomerContext> } | null>(null)

  useEffect(() => {
    let current = true
    void load(ticketId).then((result) => current && setRead({ key, result }))
    return () => {
      current = false
    }
  }, [key, ticketId, load])

  // What is on screen belongs to the case and the attempt that asked for it; anything else is still being read.
  const result = read?.key === key ? read.result : null
  return <CustomerContextView result={result} onRetry={() => setAttempt((n) => n + 1)} caseLink={caseLink} />
}

/** The section for a result already read (`null` while it is being read). */
export function CustomerContextView({ result, onRetry, caseLink }: { result: Result<CustomerContext> | null; onRetry?: () => void; caseLink?: Props['caseLink'] }) {
  const t = useT()
  const { locale } = useI18n()
  return (
    <section className="op-block op-ctx" aria-label={t('operator.context.title')} aria-busy={result === null || undefined}>
      <div className="op-block__head">
        <h2>{t('operator.context.title')}</h2>
        {result?.ok && result.data.warehouse.as_of && <span className="op-muted op-mono">{t('operator.context.asOf', { date: result.data.warehouse.as_of })}</span>}
      </div>
      {result === null ? (
        <p className="op-muted" role="status">{t('operator.context.loading')}</p>
      ) : !result.ok ? (
        <div className="op-ctx__off" role="status">
          <p>{result.status === 401 || result.status === 0 ? t(explainKey(result.status)) : t('operator.context.unavailable')}</p>
          {onRetry && result.status !== 401 && result.status !== 0 && <Button variant="ghost" tinted size="xs" onClick={onRetry}>{t('operator.retry')}</Button>}
        </div>
      ) : (
        <ContextBody data={result.data} locale={locale} caseLink={caseLink} onRetry={onRetry} />
      )}
    </section>
  )
}

function ContextBody({ data, locale, caseLink, onRetry }: { data: CustomerContext; locale: Parameters<typeof ago>[1]; caseLink?: Props['caseLink']; onRetry?: () => void }) {
  const t = useT()
  const pending = data.movements.filter((m) => m.pending).length
  return (
    <>
      <p className="op-muted op-ctx__note">{t('operator.context.note')}</p>
      {!data.warehouse.available ? (
        <div className="op-ctx__off" role="status">
          <p>{t('operator.context.warehouseDown')}</p>
          {onRetry && <Button variant="ghost" tinted size="xs" onClick={onRetry}>{t('operator.retry')}</Button>}
        </div>
      ) : (
        <>
          <h3>{t('operator.context.products')}</h3>
          {data.products.length === 0 ? <p className="op-muted">{t('operator.context.noProducts')}</p> : (
            <ul className="op-plain op-ctx__list">
              {data.products.map((p) => (
                <li key={p.product_id} data-inactive={p.status && p.status !== 'Active' ? '' : undefined}>
                  <span>{productTypeName(t, p.type)}</span>
                  <span className="op-mono op-muted">
                    <span aria-hidden="true">{maskOf(p.last4)}</span>
                    {p.last4 && <span className="sr-only">{t('operator.context.endsIn', { last4: p.last4 })}</span>}
                    {p.currency ? ` · ${p.currency}` : ''}
                  </span>
                  <span className="op-muted">{productStatusName(t, p.status)}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="op-block__head">
            <h3>{t('operator.context.movements')}</h3>
            {pending > 0 && <span className="op-mono">{t('operator.context.pendingCount', { count: pending })}</span>}
          </div>
          {data.movements.length === 0 ? <p className="op-muted">{t('operator.context.noMovements')}</p> : (
            <table className="op-ev op-ctx__moves">
              <caption className="sr-only">{t('operator.context.movements')}</caption>
              <thead>
                <tr>
                  <th scope="col">{t('operator.context.columns.date')}</th>
                  <th scope="col">{t('operator.context.columns.detail')}</th>
                  <th scope="col" className="op-ev__end">{t('operator.context.columns.amount')}</th>
                </tr>
              </thead>
              <tbody>
                {data.movements.map((m) => (
                  <tr key={m.transaction_id} data-pending={m.pending ? '' : undefined}>
                    <td className="op-mono" title={m.transaction_id}>{shortStamp(m.date)}</td>
                    <td>
                      {[movementTypeName(t, m.type), m.merchant].filter(Boolean).join(' · ')}
                      {(m.pending || (m.status && m.status !== 'Approved')) && <span className="op-tag op-tag--neutral">{movementStatusName(t, m.status)}</span>}
                    </td>
                    <td className="op-mono op-ev__end">{money(m.amount, m.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <h3>{t('operator.context.cases')}</h3>
      {data.cases.length === 0 ? <p className="op-muted">{t('operator.context.noCases')}</p> : (
        <ul className="op-plain op-ctx__list">
          {data.cases.map((c) => {
            const id = <span className="op-mono">{c.ticket_id.slice(0, 8)}</span>
            return (
              <li key={c.ticket_id}>
                <span>{caseLink ? caseLink(c.ticket_id, id) : id} · {categoryName(t, c.category)}</span>
                <span className="op-muted">{c.status && Object.hasOwn(statusKey, c.status) ? t(statusKey[c.status as DeskStatus]) : c.status ?? '—'}</span>
                <span className="op-mono op-muted">{ago(c.created_at, locale)}</span>
              </li>
            )
          })}
        </ul>
      )}

      <h3>{t('operator.context.traces')}</h3>
      {data.traces.length === 0 ? <p className="op-muted">{t('operator.context.noTraces')}</p> : (
        <ul className="op-plain op-ctx__list">
          {data.traces.map((r) => (
            <li key={r.trace_id}>
              <span><span className="op-mono">{r.trace_id}</span></span>
              <span className="op-muted">{r.transaction_id ? t('operator.context.traceOf', { id: r.transaction_id }) : '—'} · {traceStatusName(t, r.status)}</span>
              <span className="op-mono op-muted">{ago(r.created_at, locale)}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
