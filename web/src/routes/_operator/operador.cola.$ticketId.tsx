import { createFileRoute, Link, useNavigate, useRouter } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import { actOnTicket, loadTicket } from '../../server/operator.functions'
import { OperatorKeyForm } from '../-operator/OperatorKeyForm'
import { isAutomatic } from '../-operator/refresh'
import { TicketPanel } from '../-operator/TicketPanel'
import { Notice } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/cola/$ticketId')({
  loader: ({ params }) => loadTicket({ data: { ticket_id: params.ticketId, auto: isAutomatic() } }),
  head: ({ matches }) => headTitle(matches, 'operator.pageTitle.ticket'),
  component: TicketPage,
})

function TicketPage() {
  const t = useT()
  const result = Route.useLoaderData()
  const { view } = Route.useRouteContext()
  const router = useRouter()
  const navigate = useNavigate()

  if (!result.ok) {
    return (
      <div className="op-ticket-empty">
        {result.status === 404 ? <Notice status={404}>{t('operator.ticket.notFound')}</Notice> : <Notice status={result.status} />}
      </div>
    )
  }

  const ticket = result.data
  return (
    <>
      <p className="op-back">
        <Link to="/operador/cola" search={(prev) => prev}>← {t('operator.ticket.back')}</Link>
      </p>
      <TicketPanel
        key={ticket.ticket_id}
        ticket={ticket}
        view={view}
        act={(action, { expectedVersion, reason }) => actOnTicket({ data: { ticket_id: ticket.ticket_id, action, expected_version: expectedVersion, reason } })}
        reload={() => router.invalidate()}
        onClose={() => void navigate({ to: '/operador/cola', search: (prev) => prev })}
        keyForm={<OperatorKeyForm flash={view.flash} />}
        traceLink={ticket.trace_id ? <Link to="/operador/trazas/$traceId" params={{ traceId: ticket.trace_id }}>{t('operator.ticket.openTrace')}</Link> : undefined}
      />
    </>
  )
}
