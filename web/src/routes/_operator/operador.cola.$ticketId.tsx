import { createFileRoute } from '@tanstack/react-router'
import { useEffect } from 'react'
import { headTitle } from '../../i18n/head'
import { actOnTicket, loadTicket } from '../../server/operator.functions'
import { useNewCases } from '../-operator/NewCases'
import { isAutomatic } from '../-operator/refresh'
import { guarded } from '../-operator/reload'
import { TicketRoute } from '../-operator/TicketRoute'

export const Route = createFileRoute('/_operator/operador/cola/$ticketId')({
  loader: ({ params }) => guarded(() => loadTicket({ data: { ticket_id: params.ticketId, auto: isAutomatic() } })),
  head: ({ matches }) => headTitle(matches, 'operator.pageTitle.ticket'),
  component: TicketPage,
})

function TicketPage() {
  const result = Route.useLoaderData()
  const { ticketId } = Route.useParams()
  const { view } = Route.useRouteContext()
  // Opening a case is looking at it: it stops being new.
  const { markSeen } = useNewCases()
  useEffect(() => markSeen([ticketId]), [ticketId, markSeen])
  return (
    <TicketRoute
      from={Route.id}
      result={result}
      ticketId={ticketId}
      view={view}
      act={(action, { expectedVersion, reason, message }) => actOnTicket({ data: { ticket_id: ticketId, action, expected_version: expectedVersion, reason, message } })}
    />
  )
}
