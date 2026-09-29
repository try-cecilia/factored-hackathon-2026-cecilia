import { useCallback, useEffect, useState } from 'react'
import { useI18n, useT } from '../i18n/context'
import type { MessageKey } from '../i18n/translate'
import { applyDemoFault, getDemoTickets, startScenario } from '../server/demo.functions'
import { Button, IconButton } from '../ui'
import type { Entry } from './conversation'
import type { DemoFault, DemoScenario, DemoTicket } from './types'
import './DemoPanel.css'

/**
 * The scenario in course. `from` is the session it was chosen in: the new one is there when `sessionRef` differs, and `base` is
 * how many replies that conversation already had (what comes after them answers the steps). `prefilled` is the last step
 * written into the composer.
 */
type Active = { scenario: DemoScenario; from: string; base: number | null; prefilled: number }

const PATHS = ['normal', 'ambiguous', 'out_of_scope', 'action', 'human', 'attack', 'failure'] as const
const DISPOSITIONS = ['AUTO_RESOLVE', 'CLARIFY', 'ABSTAIN', 'ESCALATE'] as const
const FAULTS = ['llm_outage', 'expire_session', 'clear_traces'] as const

function known<T extends string>(list: readonly T[], value: string): value is T {
  return (list as readonly string[]).includes(value)
}

// DEMO_MODE only. Everything here talks to the API's /demo endpoints through the server; the customer app works
// the same without it, and it is drawn apart, on its own panel with its own label, so nobody mistakes it for the service.
// A scenario does not send anything: it writes its next message into the chat's input, and the person sends it from there like
// any other; the steps below only read the replies the conversation gets.
export function DemoPanel({ scenarios, sessionRef, entries, pending, escalations, prefill, overlay, onSessionChanged, onClose }: {
  scenarios: DemoScenario[]
  sessionRef: string
  entries: Entry[]
  pending: boolean
  escalations: number
  /** Writes a message into the chat's input; `replace` says the person chose it, so it goes over a draft. */
  prefill: (text: string, replace: boolean) => void
  /** The panel is a drawer over the page: choosing a scenario closes it, so the input is in reach. */
  overlay: boolean
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

  // The scenarios' own texts come from the API in Spanish, English and Portuguese; an API without Portuguese gives the Spanish.
  const text = (pair: { en: string; es: string; pt?: string }) => (locale === 'pt' ? pair.pt : undefined) ?? pair.es
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
      setActive({ scenario, from: sessionRef, base: null, prefilled: -1 })
      setModelDown(scenario.fault === 'llm_outage')
      await onSessionChanged()
    } catch {
      setNote('demo.scenarios.failed')
    } finally {
      setBusy(false)
    }
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

  const replies = entries.filter((e) => e.role === 'assistant')
  const got = active && active.base !== null ? replies.slice(active.base).map((e) => e.reply.disposition) : []
  const next = got.length
  const turns = active?.scenario.turns ?? []

  // The new session is the scenario's: from then on its replies are the steps' answers.
  useEffect(() => {
    setActive((a) => (a && a.base === null && sessionRef !== a.from ? { ...a, base: replies.length } : a))
  }, [sessionRef, replies.length])

  // The step to come is written into the input: the first over what was there (the person just chose it), the ones after only
  // if the input is empty, so a message being written is not lost.
  useEffect(() => {
    if (!active || active.base === null || next <= active.prefilled || next >= turns.length) return
    setActive({ ...active, prefilled: next })
    prefill(turns[next], next === 0)
    if (next === 0 && overlay) onClose()
  }, [active, next, turns, prefill, overlay, onClose])

  function again() {
    prefill(turns[next], true)
    if (overlay) onClose()
  }

  const groups = [...new Set(scenarios.map((s) => s.path))]

  return (
    <aside className="demo" aria-labelledby="demo-title">
      <div className="demo__head">
        <span className="demo__badge">{t('demo.badge')}</span>
        <h2 id="demo-title">{t('demo.title')}</h2>
        <IconButton className="demo__close" variant="ghost" size="sm" label={t('common.close')} icon={<svg viewBox="0 0 20 20" width={14} height={14} aria-hidden="true" focusable="false"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" /></svg>} onClick={onClose} />
      </div>
      <p className="demo__lead">{t('demo.lead')}</p>

      <section aria-label={t('demo.scenarios.title')}>
        <h3>{t('demo.scenarios.title')}</h3>
        {groups.map((path) => (
          <div key={path} className="demo__group">
            <h4>{known(PATHS, path) ? t(`demo.paths.${path}`) : path}</h4>
            {scenarios.filter((s) => s.path === path).map((s) => (
              <article key={s.id} className="demo__card" aria-label={text(s.title)}>
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
                {active?.scenario.id === s.id && (
                  <section className="demo__steps-box" aria-label={t('demo.steps.label')}>
                    <ol className="demo__steps">
                      {active.scenario.turns.map((turn, i) => {
                        const expected = active.scenario.expect[i]
                        const reply = got[i]
                        const matches = !expected || expected === reply
                        return (
                          <li key={i} aria-current={active.base !== null && i === next ? 'step' : undefined}>
                            <span className="demo__quote">“{turn}”</span>
                            <span className="demo__muted">{t('demo.steps.expected', { what: expected ? disposition(expected) : t('demo.steps.anyOutcome') })}</span>
                            {reply && <span className={matches ? 'demo__ok' : 'demo__bad'}>{t(matches ? 'demo.steps.came' : 'demo.steps.cameWrong', { what: disposition(reply) })}</span>}
                          </li>
                        )
                      })}
                    </ol>
                    <div className="demo__actions">
                      {active.base !== null && next < turns.length && <Button variant="ghost" size="sm" tinted onClick={again}>{t('demo.steps.refill')}</Button>}
                      <Button variant="ghost" size="sm" onClick={() => setActive(null)}>{t('demo.steps.close')}</Button>
                    </div>
                  </section>
                )}
              </article>
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
