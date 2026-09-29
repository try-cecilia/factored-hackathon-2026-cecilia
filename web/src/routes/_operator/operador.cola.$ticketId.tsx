import { createFileRoute, Link, useRouter } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { actOnTicket, loadTicket, type DeskAction, type DeskState, type Ticket } from '../../server/operator.functions'
import { ago, CLOSED, categoryLabel, explain, label, priorityLabel, statusLabel, when } from '../-operator/format'
import { OperatorKeyForm } from '../-operator/OperatorKeyForm'
import { KeyValues, Notice, Panel } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/cola/$ticketId')({
  loader: ({ params }) => loadTicket({ data: { ticket_id: params.ticketId } }),
  head: () => ({ meta: [{ title: 'Caso · Cecilai' }] }),
  component: TicketPage,
})

const ACTIONS: Record<DeskAction, { button: string; title: string; body: string; confirm: string; reason?: boolean }> = {
  claim: {
    button: 'Tomar caso',
    title: 'Tomar este caso',
    body: 'Queda asignado a vos. Nadie más puede decidirlo mientras lo tengas; podés devolverlo cuando quieras.',
    confirm: 'Tomar caso',
  },
  approve: {
    button: 'Aprobar rastreo',
    title: 'Aprobar el rastreo',
    body: 'Se vuelve a comprobar que el movimiento siga pendiente, se abre el pedido de rastreo y se lee de vuelta para confirmarlo.',
    confirm: 'Aprobar y abrir rastreo',
  },
  reject: {
    button: 'Rechazar',
    title: 'Rechazar el pedido',
    body: 'El caso se cierra sin abrir ningún rastreo. La decisión queda registrada con tu nombre.',
    confirm: 'Rechazar caso',
    reason: true,
  },
  release: {
    button: 'Devolver al asistente',
    title: 'Devolver al asistente',
    body: 'El caso se cierra sin decisión y la conversación vuelve a la automatización.',
    confirm: 'Devolver caso',
  },
}

function outcome(action: DeskAction, state: DeskState) {
  if (action === 'claim') return 'Tomaste el caso.'
  if (action === 'reject') return 'Caso rechazado.'
  if (action === 'release') return 'Caso devuelto al asistente.'
  return state.status === 'stale'
    ? 'El movimiento ya no estaba pendiente: no se abrió ningún rastreo y el caso quedó cerrado.'
    : `Rastreo aprobado${state.trace_id ? ` (${state.trace_id})` : ''}.`
}

function TicketPage() {
  const result = Route.useLoaderData()
  if (!result.ok) {
    return result.status === 404 ? <Notice status={404}>Este caso no existe o ya se archivó.</Notice> : <Notice status={result.status} />
  }
  return <TicketView key={result.data.ticket_id} ticket={result.data} />
}

function TicketView({ ticket }: { ticket: Ticket }) {
  const { view } = Route.useRouteContext()
  const router = useRouter()
  const dialog = useRef<HTMLDialogElement>(null)
  const [choice, setChoice] = useState<DeskAction | null>(null)
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState(false)
  const [feedback, setFeedback] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  const { desk } = ticket
  const closed = CLOSED.includes(desk.status)
  const mine = view.canAct && desk.operator === view.operator

  useEffect(() => {
    if (choice && !dialog.current?.open) dialog.current?.showModal()
  }, [choice])

  async function run(action: DeskAction) {
    setPending(true)
    try {
      const result = await actOnTicket({
        data: { ticket_id: ticket.ticket_id, action, expected_version: desk.version, reason: reason || undefined },
      })
      if (result.ok) {
        setFeedback({ tone: 'ok', text: outcome(action, result.data) })
      } else {
        const detail = result.status === 409 || result.status === 400 ? result.message : undefined
        setFeedback({ tone: 'error', text: [explain(result.status, true), detail && `(${detail})`].filter(Boolean).join(' ') })
      }
      // Whatever happened, the queue and this case are re-read: a 409 means the screen was out of date.
      await router.invalidate()
    } catch {
      setFeedback({ tone: 'error', text: 'No se pudo completar la acción. Revisá el estado del caso antes de repetirla.' })
    }
    setReason('')
    setPending(false)
    dialog.current?.close()
  }

  const available: DeskAction[] = closed
    ? []
    : desk.status === 'open'
      ? ['claim']
      : mine
        ? [...(ticket.pending_action ? (['approve'] as const) : []), 'reject', 'release']
        : []
  const evidence = ticket.evidence.filter((e) => e.type === 'transaction')
  const otherEvidence = ticket.evidence.filter((e) => e.type !== 'transaction')

  return (
    <article className="op-ticket" aria-labelledby="op-ticket-title">
      <header className="op-ticket-head">
        <p className="op-back"><Link to="/operador/cola" search={(prev) => prev}>← Volver a la cola</Link></p>
        <div className="op-ticket-badges">
          <span className={`op-priority op-priority-${ticket.priority.toLowerCase()}`}>Prioridad {label(priorityLabel, ticket.priority).toLowerCase()}</span>
          <span className={`op-status op-status-${desk.status}`}>{statusLabel[desk.status]}{desk.operator && desk.status === 'claimed' ? ` · ${desk.operator}` : ''}</span>
        </div>
        <h1 id="op-ticket-title">{label(categoryLabel, ticket.category)}</h1>
        <p className="op-muted">
          Cola <span className="op-mono">{ticket.queue}</span> · {ago(ticket.created_at)} ({when(ticket.created_at)}) · caso <span className="op-mono">{ticket.ticket_id.slice(0, 8)}</span> · versión {desk.version}
        </p>
      </header>

      <div className="op-actions" role="group" aria-label="Acciones del caso">
        {feedback && <p className={feedback.tone === 'ok' ? 'op-ok' : 'op-error'} role={feedback.tone === 'ok' ? 'status' : 'alert'}>{feedback.text}</p>}
        {!view.canAct && !closed && (
          <div className="op-needkey">
            <p>Tu sesión es de solo lectura. Para actuar sobre el caso ingresá tu clave de operador.</p>
            <OperatorKeyForm />
          </div>
        )}
        {view.canAct && !closed && desk.status === 'claimed' && !mine && <p className="op-muted">Este caso lo tomó {desk.operator}. Solo esa persona puede decidirlo.</p>}
        {closed && <p className="op-muted">Caso cerrado: {statusLabel[desk.status].toLowerCase()}{desk.history.at(-1) ? ` por ${desk.history.at(-1)!.operator}` : ''}.</p>}
        {view.canAct && available.length > 0 && (
          <div className="op-buttons">
            {available.map((a) => (
              <button key={a} type="button" className={a === 'reject' ? 'op-button op-button-danger' : a === 'release' ? 'op-button op-button-quiet' : 'op-button'} onClick={() => { setFeedback(null); setChoice(a) }} disabled={pending}>
                {ACTIONS[a].button}
              </button>
            ))}
          </div>
        )}
      </div>

      <Panel title="Pedido del cliente" note={`${ticket.customer_id} · ${ticket.segment ?? '—'} · ${ticket.country ?? '—'} · ${ticket.language}`}>
        <blockquote className="op-quote">{ticket.request}</blockquote>
        {ticket.prior_requests.length > 0 && (
          <>
            <h3>Pedidos anteriores</h3>
            <ul className="op-plain">{ticket.prior_requests.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </>
        )}
      </Panel>

      <Panel title="Por qué llegó acá">
        <p>{ticket.reason}</p>
        <p className="op-muted">Regla: <span className="op-mono">{ticket.policy_rule}</span></p>
        <p><strong>Próximo paso sugerido.</strong> {ticket.suggested_next_step}</p>
        {ticket.open_questions.length > 0 && (
          <>
            <h3>Preguntas abiertas</h3>
            <ul className="op-plain">{ticket.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
          </>
        )}
      </Panel>

      {ticket.pending_action && (
        <Panel title="Acción para aprobar" note="El asistente no puede hacerlo solo.">
          <p>
            Abrir un rastreo del movimiento <span className="op-mono">{ticket.pending_action.transaction_id}</span>
            {ticket.pending_action.movement && ` (${ticket.pending_action.movement.transaction_type ?? 'movimiento'} de ${ticket.pending_action.movement.amount} ${ticket.pending_action.movement.currency ?? ''})`}.
          </p>
          <p className="op-muted">
            Motivo de revisión: <span className="op-mono">{ticket.pending_action.review_reason ?? '—'}</span>
            {ticket.pending_action.age_days != null && ` · ${ticket.pending_action.age_days} días de antigüedad`}
          </p>
        </Panel>
      )}

      <Panel title="Evidencia" note={ticket.evidence.length ? `${ticket.evidence.length} elemento${ticket.evidence.length === 1 ? '' : 's'}` : undefined}>
        {ticket.evidence.length === 0 && <p className="op-muted">Este caso no trae evidencia adjunta.</p>}
        {evidence.length > 0 && (
          <div className="op-table-wrap">
            <table className="op-table">
              <caption className="op-sr">Movimientos recientes del cliente</caption>
              <thead>
                <tr><th scope="col">Movimiento</th><th scope="col">Fecha</th><th scope="col" className="op-num">Monto</th><th scope="col">Comercio</th><th scope="col">País</th><th scope="col">Estado</th><th scope="col" className="op-num">Riesgo</th></tr>
              </thead>
              <tbody>
                {evidence.map((e) => (
                  <tr key={e.id} className={e.flagged ? 'op-flagged' : undefined}>
                    <th scope="row" className="op-mono">{e.id}{e.flagged && <span className="op-flag"> Marcado</span>}</th>
                    <td>{String(e.detail.transaction_date ?? '—')}</td>
                    <td className="op-num">{String(e.detail.amount ?? '—')} {String(e.detail.currency ?? '')}</td>
                    <td>{String(e.detail.merchant_name ?? '—')}</td>
                    <td>{String(e.detail.transaction_country ?? '—')}</td>
                    <td>{String(e.detail.transaction_status ?? '—')}</td>
                    <td className="op-num">{String(e.detail.fraud_score ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {otherEvidence.map((e, i) => (
          <div key={i}>
            <h3>{e.type}{e.id ? ` · ${e.id}` : ''}</h3>
            <KeyValues data={e.detail} />
          </div>
        ))}
      </Panel>

      {ticket.verified_facts.length > 0 && (
        <Panel title="Hechos verificados">
          {ticket.verified_facts.map((f, i) => <KeyValues key={i} data={f} />)}
        </Panel>
      )}

      {ticket.actions_taken.length > 0 && (
        <Panel title="Lo que hizo el asistente">
          <ul className="op-plain">
            {ticket.actions_taken.map((a, i) => (
              <li key={i}><span className="op-mono">{String(a.tool ?? a.tool_name ?? 'herramienta')}</span>{a.error_type ? ` · ${String(a.error_type)}` : ''}</li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="Historial del caso" note="Cada decisión queda con el nombre de la clave que la firmó.">
        {desk.history.length === 0 ? (
          <p className="op-muted">Nadie actuó todavía.</p>
        ) : (
          <ol className="op-history">
            {desk.history.map((h, i) => (
              <li key={i}><span className="op-mono">{when(h.ts)}</span> <strong>{h.operator}</strong> · {h.action}{typeof h.detail.reason === 'string' && h.detail.reason ? ` — “${h.detail.reason}”` : ''}</li>
            ))}
          </ol>
        )}
        {ticket.trace_id && <p><Link to="/operador/trazas/$traceId" params={{ traceId: ticket.trace_id }}>Ver la traza del turno que lo originó</Link></p>}
      </Panel>

      <dialog ref={dialog} className="op-dialog" aria-labelledby="op-dialog-title" onClose={() => { setChoice(null); setReason('') }}>
        {choice && (
          <form method="dialog" onSubmit={(e) => { e.preventDefault(); void run(choice) }}>
            <h2 id="op-dialog-title">{ACTIONS[choice].title}</h2>
            <p>{ACTIONS[choice].body}</p>
            <p className="op-muted">Caso <span className="op-mono">{ticket.ticket_id.slice(0, 8)}</span> · {label(categoryLabel, ticket.category)} · actuás como <strong>{view.operator}</strong>.</p>
            {ACTIONS[choice].reason && (
              <label className="op-field">
                Motivo (opcional)
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} rows={3} />
              </label>
            )}
            <div className="op-buttons">
              <button type="button" className="op-button op-button-quiet" onClick={() => dialog.current?.close()} disabled={pending}>Cancelar</button>
              <button type="submit" className={choice === 'reject' ? 'op-button op-button-danger' : 'op-button'} disabled={pending}>{pending ? 'Enviando…' : ACTIONS[choice].confirm}</button>
            </div>
          </form>
        )}
      </dialog>
    </article>
  )
}
