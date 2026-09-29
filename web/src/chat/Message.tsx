import { useCallback, useEffect, useState } from 'react'
import { getCase } from '../server/chat.functions'
import { toBlocks, parseOptions, optionAnswer } from './format'
import { AlertIcon, CopyIcon } from './icons'
import type { CaseStatus, Reply, SendFailure, Why } from './types'

export type Entry =
  | { id: number; role: 'user'; text: string; at: Date }
  | { id: number; role: 'assistant'; reply: Reply; at: Date }
  | { id: number; role: 'error'; failure: SendFailure; text: string; key: string; at: Date }

const time = new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' })

function Avatar({ assistant, name }: { assistant: boolean; name: string }) {
  return assistant ? (
    <div className="avatar avatar-assistant" aria-hidden="true">
      <img src="/cecilia-avatar.png" alt="" width={36} height={36} />
    </div>
  ) : (
    <div className="avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</div>
  )
}

function Byline({ name, assistant, at }: { name: string; assistant: boolean; at?: Date }) {
  return (
    <div className="byline">
      <span className="byline-name">{name}</span>
      {assistant && <span className="badge-ai">IA</span>}
      {at && <time dateTime={at.toISOString()}>{time.format(at)}</time>}
    </div>
  )
}

export function Text({ text, lang }: { text: string; lang?: string }) {
  return (
    <div className="msg-text" lang={lang}>
      {toBlocks(text).map((block, i) =>
        block.type === 'ul' ? (
          <ul key={i}>{block.items.map((item, j) => <li key={j}>{item}</li>)}</ul>
        ) : (
          <p key={i}>{block.text}</p>
        ),
      )}
    </div>
  )
}

export function UserMessage({ entry }: { entry: Extract<Entry, { role: 'user' }> }) {
  return (
    <article className="msg" aria-label="Tu mensaje">
      <Avatar assistant={false} name="Vos" />
      <div className="msg-body">
        <Byline name="Vos" assistant={false} at={entry.at} />
        <Text text={entry.text} />
      </div>
    </article>
  )
}

export function Thinking() {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 8_000)
    return () => clearTimeout(timer)
  }, [])
  return (
    <article className="msg" aria-label="Cecilia está respondiendo">
      <Avatar assistant name="" />
      <div className="msg-body">
        <Byline name="Cecilia" assistant />
        <div className="thinking" role="status">
          <span className="dots" aria-hidden="true"><i /><i /><i /></span>
          {slow ? 'Sigue trabajando en tu consulta…' : 'Revisando tus cuentas'}
        </div>
      </div>
    </article>
  )
}

const failureCopy: Record<Exclude<SendFailure, 'session_expired'>, string> = {
  // After a dropped connection or a timeout nobody knows whether the message arrived. Retrying is safe: the message
  // travels with the same key, and the API answers a repeated key with the first reply instead of running it again.
  unavailable: 'No pude confirmar si el servicio recibió tu mensaje. Podés reintentar: si ya lo recibió, no se repite.',
  timeout: 'Tardó demasiado en responder y no pude confirmar si tu mensaje llegó. Podés reintentar: si ya lo recibió, no se repite.',
  rate_limited: 'Estás enviando mensajes muy rápido. Esperá un minuto y volvé a intentar.',
  busy: 'Todavía estoy respondiendo tu mensaje anterior. Esperá un momento y volvé a intentar.',
  unexpected: 'Recibí una respuesta que no pude mostrar. Probá de nuevo en un momento.',
}

export function ErrorMessage({ entry, active, onRetry }: {
  entry: Extract<Entry, { role: 'error' }>
  active: boolean
  onRetry: (entry: Extract<Entry, { role: 'error' }>) => void
}) {
  const failure = entry.failure === 'session_expired' ? 'unexpected' : entry.failure
  return (
    <article className="msg" aria-label="Aviso de Cecilia">
      <Avatar assistant name="" />
      <div className="msg-body">
        <Byline name="Cecilia" assistant at={entry.at} />
        <div className="callout callout-danger" role="alert">
          <AlertIcon />
          <span>{failureCopy[failure]}</span>
        </div>
        {active && (
          <div className="actions">
            <button type="button" className="btn btn-secondary" onClick={() => onRetry(entry)}>Reintentar</button>
          </div>
        )}
      </div>
    </article>
  )
}

const answers = {
  es: { yes: 'Sí', no: 'No', yesLabel: 'Sí, abrir el pedido', noLabel: 'No, gracias' },
  pt: { yes: 'Sim', no: 'Não', yesLabel: 'Sim, abrir o pedido', noLabel: 'Não, obrigado' },
}

const statusLabel: Record<string, string> = {
  open: 'Recibido',
  claimed: 'En revisión',
  approved: 'Aprobado',
  rejected: 'Rechazado',
  handed_back: 'Devuelto al asistente',
  stale: 'Sin cambios necesarios',
}

function CaseCard({ ticketId, onSessionExpired }: { ticketId: string; onSessionExpired: () => void }) {
  const [state, setState] = useState<{ status: 'loading' } | { status: 'error' } | { status: 'ready'; case: CaseStatus }>({ status: 'loading' })
  const [copied, setCopied] = useState(false)

  const load = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      const result = await getCase({ data: { ticket_id: ticketId } })
      if (result.ok) setState({ status: 'ready', case: result.case })
      else if (result.failure === 'session_expired') onSessionExpired()
      else setState({ status: 'error' })
    } catch {
      setState({ status: 'error' })
    }
  }, [ticketId, onSessionExpired])

  useEffect(() => { void load() }, [load])

  async function copy() {
    try {
      await navigator.clipboard.writeText(ticketId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2_000)
    } catch {
      // Clipboard blocked: the number is on screen to read out.
    }
  }

  return (
    <section className="case" aria-label="Estado de tu caso">
      <div className="case-head">
        <div>
          <div className="case-label">Número de caso</div>
          <code className="case-id">{ticketId}</code>
        </div>
        <button type="button" className="btn btn-quiet" onClick={copy}>
          <CopyIcon />{copied ? 'Copiado' : 'Copiar'}
        </button>
      </div>
      <div className="case-status" aria-live="polite">
        {state.status === 'loading' && <span className="muted">Consultando el estado…</span>}
        {state.status === 'error' && <span className="muted">No pude consultar el estado ahora.</span>}
        {state.status === 'ready' && (
          <>
            <span className={`status status-${state.case.status}`}>{statusLabel[state.case.status] ?? state.case.status}</span>
            <span>{state.case.message ?? 'Un agente va a revisar tu caso. Tu conversación viaja con él.'}</span>
          </>
        )}
      </div>
      <button type="button" className="btn btn-quiet" onClick={load} disabled={state.status === 'loading'}>
        Actualizar estado
      </button>
    </section>
  )
}

export function AssistantMessage({ entry, active, busy, onAnswer, onSessionExpired }: {
  entry: Extract<Entry, { role: 'assistant' }>
  active: boolean
  busy: boolean
  onAnswer: (text: string) => void
  onSessionExpired: () => void
}) {
  const { reply } = entry
  const lang = reply.language === 'pt' ? 'pt' : 'es'
  const proposal = reply.disposition === 'CLARIFY' && reply.category === 'confirm_action'
  const options = reply.disposition === 'CLARIFY' && !proposal ? parseOptions(reply.response_text) : null

  return (
    <article className="msg" aria-label="Respuesta de Cecilia">
      <Avatar assistant name="" />
      <div className="msg-body">
        <Byline name="Cecilia" assistant at={entry.at} />
        {options ? (
          <>
            <Text text={options.lead} lang={lang} />
            <ol className="options">
              {options.options.map((label, i) => (
                <li key={i}>
                  <button
                    type="button"
                    className="option"
                    disabled={!active || busy}
                    onClick={() => onAnswer(optionAnswer(options, i))}
                  >
                    <span className="option-n" aria-hidden="true">{i + 1}</span>
                    <span lang={lang}>{label}</span>
                  </button>
                </li>
              ))}
            </ol>
            {options.tail && <Text text={options.tail} lang={lang} />}
          </>
        ) : (
          <Text text={reply.response_text} lang={lang} />
        )}
        {proposal && (
          <div className="actions" role="group" aria-label="Confirmar el pedido de rastreo">
            <button type="button" className="btn btn-primary" disabled={!active || busy} onClick={() => onAnswer(answers[lang].yes)}>
              {answers[lang].yesLabel}
            </button>
            <button type="button" className="btn btn-secondary" disabled={!active || busy} onClick={() => onAnswer(answers[lang].no)}>
              {answers[lang].noLabel}
            </button>
          </div>
        )}
        {reply.disposition === 'ESCALATE' && reply.ticket_id && (
          <CaseCard ticketId={reply.ticket_id} onSessionExpired={onSessionExpired} />
        )}
        {reply.why && <WhyPanel why={reply.why} />}
      </div>
    </article>
  )
}

// DEMO_MODE only: the API sends `why` in the sandbox and nowhere else.
function WhyPanel({ why }: { why: Why }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="demo-box">
      <button type="button" className="btn btn-quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="badge-demo">Demo</span> {open ? 'Ocultar' : '¿Por qué?'}
      </button>
      {open && (
        <dl className="why">
          <dt>Motivo</dt>
          <dd>{why.because.es}</dd>
          <dt>Regla</dt>
          <dd><code>{why.rule}</code></dd>
          <dt>El modelo recibió</dt>
          <dd>{why.model.called ? <code>{why.model.saw}</code> : 'Nada: se resolvió en el código, sin llamar al modelo.'}</dd>
          <dt>El modelo eligió</dt>
          <dd>
            {why.model.chose.length
              ? why.model.chose.map((c, i) => <div key={i}><code>{c.tool}({JSON.stringify(c.args)})</code></div>)
              : 'Ninguna consulta.'}
          </dd>
          <dt>El código verificó</dt>
          <dd>
            {why.checks.length
              ? why.checks.map((c, i) => (
                  <div key={i}>{c.ok ? '✓' : '✗'} <code>{c.tool}</code>{c.product ? ` · ${c.product}` : ''} · {c.outcome}</div>
                ))
              : 'Ninguna consulta.'}
          </dd>
          <dt>Costo</dt>
          <dd>{why.llm_calls} {why.llm_calls === 1 ? 'llamada' : 'llamadas'} · {Math.round(why.latency_ms)} ms</dd>
        </dl>
      )}
    </div>
  )
}
