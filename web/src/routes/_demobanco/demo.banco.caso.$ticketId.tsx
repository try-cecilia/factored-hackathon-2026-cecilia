import { createFileRoute, Link, useNavigate, useRouter } from '@tanstack/react-router'
import { useMemo } from 'react'
import { useT } from '../../i18n/context'
import { headTitle } from '../../i18n/head'
import { actOnDemoTicket, loadDemoCustomerContext, loadDemoTicket } from '../../server/demo-desk.functions'
import { DEMO_ACTOR } from '../../server/demo-desk-core'
import { resultLabel } from '../-demo/results'
import { guarded, readAgain } from '../-operator/reload'
import { TicketScreen } from '../-operator/TicketScreen'

export const Route = createFileRoute('/_demobanco/demo/banco/caso/$ticketId')({
  loader: ({ params }) => guarded(() => loadDemoTicket({ data: { ticket_id: params.ticketId } })),
  head: ({ matches }) => headTitle(matches, 'demoMode.desk.pageTitle.ticket'),
  component: DemoTicketPage,
})

// The visitor acts as the demo's fixed actor: what is theirs on the desk is what "demo" holds.
const VIEW = { canAct: true, operator: DEMO_ACTOR }
const readContext = (ticketId: string) => guarded(() => loadDemoCustomerContext({ data: { ticket_id: ticketId } }))

/**
 * One case of the visitor's, on the console's own screen: take it, resolve it with a predefined result of its family and an optional
 * message, approve or reject the action it carries, or release it. Versions and 409s are the console's. No trace link, no key form.
 */
function DemoTicketPage() {
  const t = useT()
  const result = Route.useLoaderData()
  const { ticketId } = Route.useParams()
  const router = useRouter()
  const navigate = useNavigate()
  const codes = result.ok ? result.data.resolve_results : null
  const resolveOptions = useMemo(() => codes?.map((code) => ({ code, label: resultLabel(t, code) })), [codes, t])
  return (
    <>
      <p className="op-back">
        <Link to="/demo/banco">← {t('demoMode.desk.back')}</Link>
      </p>
      <TicketScreen
        ticketId={ticketId}
        result={result}
        view={VIEW}
        act={(action, { expectedVersion, reason, message, resultCode }) =>
          actOnDemoTicket({ data: { ticket_id: ticketId, action, expected_version: expectedVersion, reason, message, result_code: resultCode } })}
        reload={(minVersion) => readAgain(router, Route.id, ticketId, minVersion)}
        onClose={() => void navigate({ to: '/demo/banco' })}
        keyForm={null}
        loadContext={readContext}
        caseLink={(id, label) => <Link to="/demo/banco/caso/$ticketId" params={{ ticketId: id }}>{label}</Link>}
        resolveOptions={resolveOptions}
        auditNote={t('demoMode.desk.mine')}
      />
    </>
  )
}
