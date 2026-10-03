import { Link } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import './demo-mode.css'

/**
 * "Tu caso ya llegó al banco" (Paper "Puente al banco"): in the customer's view of the one-click demo, once the conversation has a
 * case a person has not decided yet. One click takes the visitor to that same case on the bank's side.
 */
export function BankBridgeCard({ ticketId }: { ticketId: string }) {
  const t = useT()
  return (
    <section className="demo-bridge" aria-label={t('demoMode.bridge.title')}>
      <h2>{t('demoMode.bridge.title')}</h2>
      <p>{t('demoMode.bridge.body')}</p>
      <Link className="demo-bridge__action" to="/demo/banco/caso/$ticketId" params={{ ticketId }}>
        {t('demoMode.bridge.action')} <span aria-hidden="true">→</span>
      </Link>
    </section>
  )
}
