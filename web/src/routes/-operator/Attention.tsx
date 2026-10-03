import { useT } from '../../i18n/context'
import type { CustomerContext } from '../../server/customer-context'
import type { Ticket } from '../../server/operator.functions'
import { money, shortStamp } from './format'
import { isInactive, movementTypeName, productStatusName, productTypeName } from './context'
import { isFlagged, scoreLabel } from './summary'

/**
 * What the operator should look at before anything else: the customer's movements still pending, their products that are not
 * active and the movements the assistant flagged. Nothing new is decided here, it only gathers what the case and the customer's
 * context already say; with nothing to show, the card is not drawn.
 */
export function Attention({ ticket, data }: { ticket: Ticket; data: CustomerContext | null }) {
  const t = useT()
  const warehouse = data?.warehouse.available ? data : null
  const pending = warehouse?.movements.filter((m) => m.pending) ?? []
  const products = warehouse?.products.filter(isInactive) ?? []
  const flagged = ticket.evidence.filter(isFlagged)
  if (!pending.length && !products.length && !flagged.length) return null
  return (
    <section className="op-sheet op-attention" aria-label={t('operator.ticket.attention.title')}>
      <h2>{t('operator.ticket.attention.title')}</h2>
      <ul className="op-plain">
        {pending.map((m) => (
          <li key={`pending:${m.transaction_id}`}>
            <span className="op-attention__title">{t('operator.ticket.attention.pendingMovement', { type: movementTypeName(t, m.type) })}</span>
            <span className="op-mono">{money(m.amount, m.currency, ticket.country)}</span>
            <span className="op-mono op-attention__sub">{shortStamp(m.date)}</span>
          </li>
        ))}
        {flagged.map((e, i) => (
          <li key={`flagged:${e.id ?? i}`}>
            <span className="op-attention__title">{t('operator.ticket.attention.flaggedMovement')}</span>
            <span className="op-mono">{money(e.detail.amount, e.detail.currency, ticket.country)}</span>
            <span className="op-mono op-attention__sub">{[shortStamp(e.detail.transaction_date), e.detail.merchant_name, t('operator.ticket.attention.score', { score: scoreLabel(e) })].filter(Boolean).map(String).join(' · ')}</span>
          </li>
        ))}
        {products.map((p) => (
          <li key={`product:${p.product_id}`} data-product="">
            <span className="op-attention__title">
              {productTypeName(t, p.type)}
              {p.last4 && <> <span aria-hidden="true">··{p.last4}</span><span className="sr-only">{t('operator.context.endsIn', { last4: p.last4 })}</span></>}
            </span>
            <span className="op-attention__state">{productStatusName(t, p.status)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
