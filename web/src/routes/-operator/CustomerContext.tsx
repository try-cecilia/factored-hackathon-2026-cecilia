import { useEffect, useState, type ReactNode } from 'react'
import { useI18n, useT } from '../../i18n/context'
import type { CustomerContext } from '../../server/customer-context'
import type { DeskStatus, Result } from '../../server/operator.functions'
import { Button } from '../../ui'
import { ago, categoryName, CLOSED, explainKey, money, shortStamp, statusKey } from './format'
import { isInactive, maskOf, movementStatusName, movementTypeName, productStatusName, productTypeName, traceStatusName } from './context'
import { Fold } from './Folds'

export type CaseLink = (ticketId: string, label: ReactNode) => ReactNode

/** The movements shown under the pending ones before the operator asks for all of them. */
const RECENT = 3

/** The customer's context as the panel has it: `null` while it is being read, otherwise what the read returned. */
export type CustomerRead = { result: Result<CustomerContext> | null; retry: () => void }

/**
 * Reads the customer beside the case, on its own and once the case is on screen, so a slow or absent warehouse never delays or
 * breaks the case. It never throws: a failure is a `{ ok: false }` result (see `guarded`). A later answer for another case, or
 * for an attempt that was replaced, is dropped.
 */
export function useCustomerContext(ticketId: string, load?: (ticketId: string) => Promise<Result<CustomerContext>>): CustomerRead & { enabled: boolean } {
  const [attempt, setAttempt] = useState(0)
  const key = `${ticketId}:${attempt}`
  const [read, setRead] = useState<{ key: string; result: Result<CustomerContext> } | null>(null)

  useEffect(() => {
    if (!load) return
    let current = true
    void load(ticketId).then((result) => current && setRead({ key, result }))
    return () => {
      current = false
    }
  }, [key, ticketId, load])

  // What is on screen belongs to the case and the attempt that asked for it; anything else is still being read.
  return { enabled: !!load, result: read?.key === key ? read.result : null, retry: () => setAttempt((n) => n + 1) }
}

/** What stands in the sections while the customer cannot be shown: reading, failed, or a warehouse that is down. Nothing when it is there. */
export function ContextNotice({ result, onRetry }: { result: Result<CustomerContext> | null; onRetry: () => void }) {
  const t = useT()
  if (result === null) {
    return (
      <div className="op-fold op-fold--note" aria-busy="true">
        <div className="op-fold__head" role="status">
          <span className="op-fold__chevron" aria-hidden="true" />
          <span className="op-fold__title">{t('operator.context.title')}</span>
          <span className="op-fold__summary">{t('operator.context.loading')}</span>
        </div>
      </div>
    )
  }
  const down = result.ok && !result.data.warehouse.available
  if (result.ok && !down) return null
  const message = !result.ok ? (result.status === 401 || result.status === 0 ? t(explainKey(result.status)) : t('operator.context.unavailable')) : t('operator.context.warehouseDown')
  const retry = result.ok || (result.status !== 401 && result.status !== 0)
  return (
    <div className="op-fold op-fold--note">
      <div className="op-ctx__off" role="status">
        <p>{message}</p>
        {retry && <Button variant="ghost" tinted size="xs" onClick={onRetry}>{t('operator.retry')}</Button>}
      </div>
    </div>
  )
}

export function ProductsFold({ data }: { data: CustomerContext }) {
  const t = useT()
  const { products } = data
  const blocked = products.filter((p) => p.status === 'Blocked').length
  const inactive = products.filter(isInactive).length - blocked
  const summary = [
    String(products.length),
    blocked > 0 && t(blocked === 1 ? 'operator.context.blockedOne' : 'operator.context.blockedOther', { count: blocked }),
    inactive > 0 && t(inactive === 1 ? 'operator.context.inactiveOne' : 'operator.context.inactiveOther', { count: inactive }),
  ].filter(Boolean).join(' · ')
  return (
    <Fold id="products" title={t('operator.context.products')} summary={products.length ? summary : t('operator.ticket.sections.none')} empty={products.length === 0}>
      <p className="op-muted op-ctx__note">{t('operator.context.note')}</p>
      <ul className="op-plain op-ctx__list">
        {products.map((p) => (
          <li key={p.product_id} data-inactive={isInactive(p) ? '' : undefined}>
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
    </Fold>
  )
}

/** `inEvidence`: ids of the movements the case already shows in its Evidence section; here they are marked, so the same movement is not read twice as if it were two. */
export function MovementsFold({ data, inEvidence }: { data: CustomerContext; inEvidence?: ReadonlySet<string> }) {
  const t = useT()
  const [all, setAll] = useState(false)
  const { movements } = data
  const pending = movements.filter((m) => m.pending)
  const rest = movements.filter((m) => !m.pending)
  // The pending ones stay on top, highlighted; below them the most recent, until the operator asks for the rest.
  const shown = [...pending, ...(all ? rest : rest.slice(0, RECENT))]
  const summary = pending.length > 0 ? t(pending.length === 1 ? 'operator.context.pendingCountOne' : 'operator.context.pendingCountOther', { count: pending.length }) : String(movements.length)
  return (
    <Fold id="movements" title={t('operator.context.movements')} summary={movements.length ? summary : t('operator.ticket.sections.none')} tone={pending.length > 0 ? 'alert' : undefined} empty={movements.length === 0}>
      <ul className="op-plain op-moves">
        {shown.map((m) => (
          <li key={m.transaction_id} data-pending={m.pending ? '' : undefined}>
            <span className="op-mono op-muted" title={m.transaction_id}>{shortStamp(m.date)}</span>
            <span>
              {[movementTypeName(t, m.type), m.merchant].filter(Boolean).join(' · ')}
              {(m.pending || (m.status && m.status !== 'Approved')) && <span className="op-tag op-tag--neutral">{movementStatusName(t, m.status)}</span>}
              {inEvidence?.has(m.transaction_id) && <span className="op-tag op-tag--info" title={t('operator.context.inEvidenceHint')}>{t('operator.context.inEvidence')}</span>}
            </span>
            <span className="op-mono">{money(m.amount, m.currency)}</span>
          </li>
        ))}
      </ul>
      {data.pending_omitted > 0 && <p className="op-muted op-ctx__more">{data.pending_omitted === 1 ? t('operator.context.pendingMoreOne') : t('operator.context.pendingMoreOther', { count: data.pending_omitted })}</p>}
      {!all && rest.length > RECENT && <button type="button" className="op-link" onClick={() => setAll(true)}>{t('operator.context.viewAll', { count: movements.length })}</button>}
      {data.warehouse.as_of && <p className="op-muted op-mono op-ctx__more">{t('operator.context.asOf', { date: data.warehouse.as_of })}</p>}
    </Fold>
  )
}

export function CasesFold({ data, caseLink }: { data: CustomerContext; caseLink?: CaseLink }) {
  const t = useT()
  const { locale } = useI18n()
  const { cases } = data
  const open = cases.filter((c) => c.status && !CLOSED.includes(c.status as DeskStatus)).length
  const summary = [String(cases.length), open > 0 && t(open === 1 ? 'operator.context.openOne' : 'operator.context.openOther', { count: open })].filter(Boolean).join(' · ')
  return (
    <Fold id="cases" title={t('operator.context.cases')} summary={cases.length ? summary : t('operator.ticket.sections.none')} empty={cases.length === 0}>
      <ul className="op-plain op-ctx__list">
        {cases.map((c) => {
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
    </Fold>
  )
}

export function TracesFold({ data }: { data: CustomerContext }) {
  const t = useT()
  const { locale } = useI18n()
  const { traces } = data
  return (
    <Fold id="traces" title={t('operator.context.traces')} summary={traces.length ? String(traces.length) : t('operator.ticket.sections.none')} empty={traces.length === 0}>
      <ul className="op-plain op-ctx__list">
        {traces.map((r) => (
          <li key={r.trace_id}>
            <span><span className="op-mono">{r.trace_id}</span></span>
            <span className="op-muted">{r.transaction_id ? t('operator.context.traceOf', { id: r.transaction_id }) : '—'} · {traceStatusName(t, r.status)}</span>
            <span className="op-mono op-muted">{ago(r.created_at, locale)}</span>
          </li>
        ))}
      </ul>
    </Fold>
  )
}
