import { Link, useNavigate, useRouter } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import { loadCustomerContext, type Result, type Ticket } from '../../server/operator.functions'
import { CustomerContextSection } from './CustomerContext'
import { OperatorKeyForm } from './OperatorKeyForm'
import { guarded, readAgain } from './reload'
import type { TicketPanelProps } from './TicketPanel'
import { TicketScreen } from './TicketScreen'

type Props = {
  /** Id of the route that reads the case: its match is what a reload has to end well. */
  from: string
  result: Result<Ticket>
  ticketId: string
  view: TicketPanelProps['view'] & { flash?: string | null }
  act: TicketPanelProps['act']
}

const readContext = (ticketId: string) => guarded(() => loadCustomerContext({ data: { ticket_id: ticketId } }))

/** The case of the URL, wired to the router: back link, close button, trace link, and a reload that says whether it worked. */
export function TicketRoute({ from, result, ticketId, view, act }: Props) {
  const t = useT()
  const router = useRouter()
  const navigate = useNavigate()
  return (
    <>
      <p className="op-back">
        <Link to="/operador/cola" search={(prev) => prev}>← {t('operator.ticket.back')}</Link>
      </p>
      <TicketScreen
        ticketId={ticketId}
        result={result}
        view={view}
        act={act}
        reload={(minVersion) => readAgain(router, from, ticketId, minVersion)}
        onClose={() => void navigate({ to: '/operador/cola', search: (prev) => prev })}
        keyForm={<OperatorKeyForm flash={view.flash} />}
        context={
          <CustomerContextSection
            ticketId={ticketId}
            load={readContext}
            caseLink={(id, label) => <Link to="/operador/cola/$ticketId" params={{ ticketId: id }} search={(prev) => prev}>{label}</Link>}
          />
        }
        traceLink={result.ok && result.data.trace_id ? <Link to="/operador/trazas/$traceId" params={{ traceId: result.data.trace_id }}>{t('operator.ticket.openTrace')}</Link> : undefined}
      />
    </>
  )
}
