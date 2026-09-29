import { useCallback, useEffect, useState } from 'react'
import { useI18n, useT } from '../i18n/context'
import type { MessageKey } from '../i18n/translate'
import { applyDemoFault, getDemoTickets, startScenario } from '../server/demo.functions'
import { Button, IconButton } from '../ui'
import type { DemoFault, DemoScenario, DemoTicket, Reply } from './types'
import './DemoPanel.css'

type Active = { scenario: DemoScenario; got: string[] }

const PATHS = ['normal', 'ambiguous', 'out_of_scope', 'action', 'human', 'attack', 'failure'] as const
const DISPOSITIONS = ['AUTO_RESOLVE', 'CLARIFY', 'ABSTAIN', 'ESCALATE'] as const
const FAULTS = ['llm_outage', 'expire_session', 'clear_traces'] as const

function known<T extends string>(list: readonly T[], value: string): value is T {
  return (list as readonly string[]).includes(value)
}

// DEMO_MODE only. Everything here talks to the API's /demo endpoints through the server; the customer app works
// the same without it, and it is drawn apart, on its own panel with its own label, so nobody mistakes it for the service.
export function DemoPanel({ scenarios, sessionRef, pending, escalations, send, onSessionChanged, onClose }: {
  scenarios: DemoScenario[]
  sessionRef: string
  pending: boolean
  escalations: number
  send: (text: string) => Promise<Reply | null>
  onSessionChanged: () => Promise<void>
  onClose: () => void
}) {
  const t = useT()
  const { locale } = useI18n()
  const [active, setActive] = useState<Active | null>(null)
  const [busy, setBusy] = useState(false)
  const [modelDown, setModelDown] = useState(false)
  const [note, setNote] = useState<MessageKey | null>(null)
  const [tickets, setTickets] = useState<DemoTicket[]>([])

  // The scenarios' own texts come from the API in Spanish and English: Portuguese readers get the Spanish.
  const text = (pair: { en: string; es: string }) => pair.es
  const disposition = (value: string) => (known(DISPOSITIONS, value) ? t(`demo.dispositions.${value}`) : value)

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
      if (!result.ok) return setNote('demo.scenarios.failed')
      setActive({ scenario, got: [] })
      setModelDown(scenario.fault === 'llm_outage')
      await onSessionChanged()
    } catch {
      setNote('demo.scenarios.failed')
    } finally {
      setBusy(false)
    }
  }

  async function sendStep() {
    if (!active) return
    const step = active.scenario.turns[active.got.length]
    const reply = await send(step)
    if (reply) setActive((a) => (a ? { ...a, got: [...a.got, reply.disposition] } : a))
  }

  async function fault(kind: DemoFault) {
    setNote(null)
    try {
      const { ok } = await applyDemoFault({ data: { fault: kind } })
      if (!ok) return setNote('demo.faults.failed')
      if (kind === 'llm_outage') setModelDown(true)
      if (kind === 'llm_restore') setModelDown(false)
      if (kind === 'expire_session') setNote('demo.faults.expired')
    } catch {
      setNote('demo.faults.failed')
    }
  }

  const groups = [...new Set(scenarios.map((s) => s.path))]
  const next = active ? active.got.length : 0

  return (
    <aside className="demo" aria-labelledby="demo-title">
      <div className="demo__head">
        <span className="demo__badge">{t('demo.badge')}</span>
        <h2 id="demo-title">{t('demo.title')}</h2>
        <IconButton className="demo__close" variant="ghost" size="sm" label={t('common.close')} icon={<svg viewBox="0 0 20 20" width={14} height={14} aria-hidden="true" focusable="false"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" /></svg>} onClick={onClose} />
      </div>
      <p className="demo__lead">{t('demo.lead')}</p>

      {active && (
        <section className="demo__card" aria-label={t('demo.steps.label')}>
          <strong>{text(active.scenario.title)}</strong>
          <ol className="demo__steps">
            {active.scenario.turns.map((turn, i) => {
              const expected = active.scenario.expect[i]
              const got = active.got[i]
              const matches = !expected || expected === got
              return (
                <li key={i}>
                  <span className="demo__quote">“{turn}”</span>
                  <span className="demo__muted">{t('demo.steps.expected', { what: expected ? disposition(expected) : t('demo.steps.anyOutcome') })}</span>
                  {got && <span className={matches ? 'demo__ok' : 'demo__bad'}>{t(matches ? 'demo.steps.came' : 'demo.steps.cameWrong', { what: disposition(got) })}</span>}
                  {i === next && <Button variant="ghost" size="sm" tinted disabled={pending} onClick={() => void sendStep()}>{t('demo.steps.send')}</Button>}
                </li>
              )
            })}
          </ol>
          <Button variant="ghost" size="sm" onClick={() => setActive(null)}>{t('demo.steps.close')}</Button>
        </section>
      )}

      <section aria-label={t('demo.scenarios.title')}>
        <h3>{t('demo.scenarios.title')}</h3>
        {groups.map((path) => (
          <div key={path} className="demo__group">
            <h4>{known(PATHS, path) ? t(`demo.paths.${path}`) : path}</h4>
            {scenarios.filter((s) => s.path === path).map((s) => (
              <div key={s.id} className="demo__card">
                <div className="demo__row">
                  <span className="demo__name">{text(s.title)}</span>
                  <span className="demo__tag" title={t('demo.scenarios.language', { lang: s.language.toUpperCase() })}>{s.language.toUpperCase()}</span>
                </div>
                <p className="demo__muted">{text(s.look_for)}</p>
                <div className="demo__row">
                  <code>{s.customer_id}{s.fault ? ` · ${known(FAULTS, s.fault) ? t(`demo.faultNotes.${s.fault}`) : s.fault}` : ''}</code>
                  <Button variant="ghost" size="sm" tinted disabled={busy || pending} onClick={() => void run(s)}>
                    {active?.scenario.id === s.id ? t('demo.scenarios.restart') : t('demo.scenarios.load')}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </section>

      <section aria-label={t('demo.faults.label')}>
        <h3>{t('demo.faults.title')}</h3>
        <div className="demo__actions">
          <Button variant="ghost" size="sm" tinted onClick={() => void fault('expire_session')}>{t('demo.faults.expire')}</Button>
          <Button variant="ghost" size="sm" tinted onClick={() => void fault(modelDown ? 'llm_restore' : 'llm_outage')}>
            {modelDown ? t('demo.faults.modelRestore') : t('demo.faults.modelDown')}
          </Button>
        </div>
        {note && <p className="demo__note" role="status">{t(note)}</p>}
      </section>

      <section aria-label={t('demo.bank.title')}>
        <div className="demo__row">
          <h3>{t('demo.bank.title')}</h3>
          <Button variant="ghost" size="sm" onClick={() => void refreshTickets()}>{t('demo.bank.refresh')}</Button>
        </div>
        {tickets.length === 0 ? (
          <p className="demo__muted">{t('demo.bank.empty')}</p>
        ) : (
          tickets.map((ticket) => (
            <article key={ticket.ticket_id} className="demo__card">
              <div className="demo__row">
                <code>{ticket.queue}</code>
                <span className="demo__tag">{ticket.priority}</span>
              </div>
              <dl className="demo__facts">
                <dt>{t('demo.bank.request')}</dt><dd>{ticket.request}</dd>
                <dt>{t('demo.bank.reason')}</dt><dd>{ticket.reason}</dd>
                <dt>{t('demo.bank.next')}</dt><dd>{ticket.suggested_next_step}</dd>
              </dl>
              <code className="demo__muted">{ticket.ticket_id}</code>
            </article>
          ))
        )}
      </section>
    </aside>
  )
}
