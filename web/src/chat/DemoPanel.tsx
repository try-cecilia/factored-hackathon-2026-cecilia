import { useCallback, useEffect, useState } from 'react'
import { applyDemoFault, getDemoTickets, startScenario } from '../server/demo.functions'
import type { DemoFault, DemoScenario, DemoTicket, Reply } from './types'

const PATHS: Record<string, string> = {
  normal: 'Normal',
  ambiguous: 'Ambiguo',
  out_of_scope: 'Fuera de alcance',
  action: 'Acción verificada',
  human: 'Requiere una persona',
  attack: 'Ataque',
  failure: 'Fallas',
}
const DISPOSITIONS: Record<string, string> = {
  AUTO_RESOLVE: 'Resuelto',
  CLARIFY: 'Pregunta',
  ABSTAIN: 'Declina',
  ESCALATE: 'A una persona',
}
const FAULT_NOTES: Record<string, string> = {
  llm_outage: 'arranca con el modelo caído',
  expire_session: 'arranca con la sesión vencida',
  clear_traces: 'arranca sin pedidos anteriores',
}

type Active = { scenario: DemoScenario; got: string[] }

// DEMO_MODE only. Everything here talks to the API's /demo endpoints through the server; the customer app works
// the same without it, and it is drawn apart, with its own label, so nobody mistakes it for the service.
export function DemoPanel({ scenarios, sessionRef, pending, escalations, send, onSessionChanged }: {
  scenarios: DemoScenario[]
  sessionRef: string
  pending: boolean
  escalations: number
  send: (text: string) => Promise<Reply | null>
  onSessionChanged: () => Promise<void>
}) {
  const [active, setActive] = useState<Active | null>(null)
  const [busy, setBusy] = useState(false)
  const [modelDown, setModelDown] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [tickets, setTickets] = useState<DemoTicket[]>([])

  const refreshTickets = useCallback(async () => {
    try {
      setTickets(await getDemoTickets())
    } catch {
      setTickets([])
    }
  }, [])

  useEffect(() => { void refreshTickets() }, [refreshTickets, sessionRef, escalations])

  async function run(scenario: DemoScenario) {
    setBusy(true)
    setNote(null)
    try {
      const result = await startScenario({ data: { id: scenario.id } })
      if (!result.ok) return setNote('No se pudo iniciar el escenario.')
      setActive({ scenario, got: [] })
      setModelDown(scenario.fault === 'llm_outage')
      await onSessionChanged()
    } catch {
      setNote('No se pudo iniciar el escenario.')
    } finally {
      setBusy(false)
    }
  }

  async function sendStep() {
    if (!active) return
    const text = active.scenario.turns[active.got.length]
    const reply = await send(text)
    if (reply) setActive((a) => (a ? { ...a, got: [...a.got, reply.disposition] } : a))
  }

  async function fault(kind: DemoFault) {
    setNote(null)
    try {
      const { ok } = await applyDemoFault({ data: { fault: kind } })
      if (!ok) return setNote('No se pudo aplicar.')
      if (kind === 'llm_outage') setModelDown(true)
      if (kind === 'llm_restore') setModelDown(false)
      if (kind === 'expire_session') setNote('Sesión vencida: el próximo mensaje te lleva a ingresar de nuevo.')
    } catch {
      setNote('No se pudo aplicar.')
    }
  }

  const groups = [...new Set(scenarios.map((s) => s.path))]
  const next = active ? active.got.length : 0

  return (
    <aside className="demo" aria-labelledby="demo-title">
      <div className="demo-head">
        <span className="badge-demo">Demo</span>
        <h2 id="demo-title">Ayudas de demostración</h2>
      </div>
      <p className="demo-lead">
        Solo existen en el entorno de prueba. Cambian de cliente, fuerzan fallas y muestran lo que ve el banco; no son parte del servicio real.
      </p>

      {active && (
        <section className="demo-steps" aria-label="Pasos del escenario">
          <strong>{active.scenario.title.es}</strong>
          <ol>
            {active.scenario.turns.map((turn, i) => {
              const expected = active.scenario.expect[i]
              const got = active.got[i]
              return (
                <li key={i}>
                  <span className="quote">“{turn}”</span>
                  <span className="muted">Esperado: {expected ? DISPOSITIONS[expected] : 'cualquiera'}</span>
                  {got && (
                    <span className={!expected || expected === got ? 'ok' : 'bad'}>
                      {!expected || expected === got ? '✓' : '✗ Salió'} {DISPOSITIONS[got] ?? got}
                    </span>
                  )}
                  {i === next && (
                    <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => void sendStep()}>
                      Enviar este mensaje
                    </button>
                  )}
                </li>
              )
            })}
          </ol>
          <button type="button" className="btn btn-quiet" onClick={() => setActive(null)}>Cerrar pasos</button>
        </section>
      )}

      <section aria-label="Escenarios guiados">
        <h3>Escenarios guiados</h3>
        {groups.map((path) => (
          <div key={path} className="demo-group">
            <h4>{PATHS[path] ?? path}</h4>
            {scenarios.filter((s) => s.path === path).map((s) => (
              <div key={s.id} className="scenario">
                <div className="scenario-title">
                  <span>{s.title.es}</span>
                  <span className="tag">{s.language.toUpperCase()}</span>
                </div>
                <p>{s.look_for.es}</p>
                <div className="scenario-foot">
                  <code>{s.customer_id}{s.fault ? ` · ${FAULT_NOTES[s.fault] ?? s.fault}` : ''}</code>
                  <button type="button" className="btn btn-secondary" disabled={busy || pending} onClick={() => void run(s)}>
                    {active?.scenario.id === s.id ? 'Reiniciar' : 'Cargar'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </section>

      <section aria-label="Fallas">
        <h3>Fallas en esta sesión</h3>
        <div className="actions">
          <button type="button" className="btn btn-secondary" onClick={() => void fault('expire_session')}>Vencer la sesión</button>
          <button type="button" className="btn btn-secondary" onClick={() => void fault(modelDown ? 'llm_restore' : 'llm_outage')}>
            {modelDown ? 'Modelo caído: restaurar' : 'Simular caída del modelo'}
          </button>
        </div>
        {note && <p className="demo-note" role="status">{note}</p>}
      </section>

      <section aria-label="Vista del banco">
        <div className="demo-row">
          <h3>Vista del banco</h3>
          <button type="button" className="btn btn-quiet" onClick={() => void refreshTickets()}>Actualizar</button>
        </div>
        {tickets.length === 0 ? (
          <p className="muted">Todavía no hay casos de esta sesión. Probá “Cargo no reconocido”.</p>
        ) : (
          tickets.map((t) => (
            <article key={t.ticket_id} className="ticket">
              <div className="scenario-title">
                <span>{t.queue}</span>
                <span className="tag">{t.priority}</span>
              </div>
              <dl>
                <dt>Pedido</dt><dd>{t.request}</dd>
                <dt>Motivo</dt><dd>{t.reason}</dd>
                <dt>Próximo paso</dt><dd>{t.suggested_next_step}</dd>
              </dl>
              <code>{t.ticket_id}</code>
            </article>
          ))
        )}
      </section>
    </aside>
  )
}
