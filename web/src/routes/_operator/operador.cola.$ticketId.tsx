import { createFileRoute, Link, useNavigate, useRouter } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import { actOnTicket, loadTicket, type Result, type Ticket } from '../../server/operator.functions'
import { OperatorKeyForm } from '../-operator/OperatorKeyForm'
import { isAutomatic } from '../-operator/refresh'
import { TicketScreen } from '../-operator/TicketScreen'

export const Route = createFileRoute('/_operator/operador/cola/$ticketId')({
  loader: ({ params }) => loadTicket({ data: { ticket_id: params.ticketId, auto: isAutomatic() } }),
  head: ({ matches }) => headTitle(matches, 'operator.pageTitle.ticket'),
  component: TicketPage,
})

function TicketPage() {
  const t = useT()
  const result = Route.useLoaderData()
  const { ticketId } = Route.useParams()
  const { view } = Route.useRouteContext()
  const router = useRouter()
  const navigate = useNavigate()

  // "Read again" is true only when the case came back: a failed read leaves the panel with what it had.
  async function reload() {
    await router.invalidate()
    const match = router.state.matches.find((m) => m.routeId === Route.id)
    return (match?.loaderData as Result<Ticket> | undefined)?.ok === true
  }

  return (
    <>
      <p className="op-back">
        <Link to="/operador/cola" search={(prev) => prev}>← {t('operator.ticket.back')}</Link>
      </p>
      <TicketScreen
        ticketId={ticketId}
        result={result}
        view={view}
        act={(action, { expectedVersion, reason }) => actOnTicket({ data: { ticket_id: ticketId, action, expected_version: expectedVersion, reason } })}
        reload={reload}
        onClose={() => void navigate({ to: '/operador/cola', search: (prev) => prev })}
        keyForm={<OperatorKeyForm flash={view.flash} />}
        traceLink={result.ok && result.data.trace_id ? <Link to="/operador/trazas/$traceId" params={{ traceId: result.data.trace_id }}>{t('operator.ticket.openTrace')}</Link> : undefined}
      />
    </>
  )
}
