import { useRef } from 'react'
import { useT } from '../../i18n/context'
import type { Result, Ticket } from '../../server/operator.functions'
import { TicketPanel, type TicketPanelProps } from './TicketPanel'
import { Notice } from './ui'

type Props = Omit<TicketPanelProps, 'ticket' | 'loadError'> & {
  /** Id of the case in the URL. */
  ticketId: string
  /** What the last read of it returned. */
  result: Result<Ticket>
}

/**
 * The case of the URL. When a read fails after the case was already on screen (the API went away for a moment), the panel
 * stays mounted with the last data it had, so the operator does not lose a 409 notice, a reason being typed or a pending
 * action; the failure shows inside the panel. A case that was never read shows the error instead.
 */
export function TicketScreen({ ticketId, result, ...panel }: Props) {
  const t = useT()
  const last = useRef<Ticket | null>(null)
  if (result.ok) last.current = result.data
  else if (last.current && last.current.ticket_id !== ticketId) last.current = null

  const shown = result.ok ? result.data : last.current
  if (!shown) {
    const status = (result as { status: number }).status
    return <div className="op-ticket-empty">{status === 404 ? <Notice status={404}>{t('operator.ticket.notFound')}</Notice> : <Notice status={status} />}</div>
  }
  return <TicketPanel key={shown.ticket_id} ticket={shown} loadError={result.ok ? undefined : result.status} {...panel} />
}
