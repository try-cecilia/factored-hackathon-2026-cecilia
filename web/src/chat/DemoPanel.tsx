import { useCallback, useEffect, useState } from 'react'
import { useI18n, useT } from '../i18n/context'
import type { MessageKey } from '../i18n/translate'
import { applyDemoFault, getDemoTickets, startScenario } from '../server/demo.functions'
import { Button, IconButton } from '../ui'
import type { Entry, UserEntry } from './conversation'
import type { DemoFault, DemoScenario, DemoTicket } from './types'
import './DemoPanel.css'

/**
 * The scenario in course. `from` is the session it was chosen in: the new one is there when `sessionRef` differs, and `base` is
 * how many entries that conversation already had (what comes after them can answer the steps). `started` says the first
 * message was sent.
 */
type Active = { scenario: DemoScenario; from: string; base: number | null; started: boolean }

const PATHS = ['normal', 'ambiguous', 'out_of_scope', 'action', 'human', 'attack', 'failure'] as const
const DISPOSITIONS = ['AUTO_RESOLVE', 'CLARIFY', 'ABSTAIN', 'ESCALATE'] as const
const FAULTS = ['llm_outage', 'expire_session', 'clear_traces'] as const

function known<T extends string>(list: readonly T[], value: string): value is T {
  return (list as readonly string[]).includes(value)
}

// DEMO_MODE only. Everything here talks to the API's /demo endpoints through the server; the customer app works
// the same without it, and it is drawn apart, on its own panel with its own label, so nobody mistakes it for the service.
// A scenario sends its messages through the chat's own send, like any suggestion: the first one when its session is up, the
// next ones with the button of the step in course. The steps below read the conversation. A step is answered when the reply is
// to the step's own text; a reply to any other message (one the person wrote by hand) is not a step (the card says so), so an
// unrelated message does not move the scenario. Each reply
// says which message it answers (`to`), because a retry's reply comes late, after other messages; the replies are read in the
// order they came.
function progress(entries: Entry[], turns: string[]): { got: string[]; off: boolean } {
  const got: string[] = []
  let off = false
  entries.forEach((entry, i) => {
    if (entry.role !== 'assistant') return
    const asked = entry.to !== undefined
      ? entries.find((e) => e.role === 'user' && e.id === entry.to)
      : entries.slice(0, i).reverse().find((e) => e.role === 'user')
    if (asked?.role !== 'user') return
    const step = turns[got.length]
    off = step === undefined || asked.text.trim() !== step.trim()
    if (!off) got.push(entry.reply.disposition)
  })
  return { got, off }
}

export function DemoPanel({ scenarios, sessionRef, entries, pending, escalations, ended, send, retry, overlay, onSessionChanged, onClose }: {
  scenarios: DemoScenario[]
  sessionRef: string
  entries: Entry[]
  pending: boolean
  escalations: number
  /** The session is over: no step can be sent (loading a scenario starts another). */
  ended: boolean
  /** The chat's own send: the messages of a scenario go through it, with the same key, the same state and the same retry. */
  send: (text: string) => Promise<unknown>
  /** Sends a message that did not go through again, with the same key (the bubble's own retry). */
  retry: (id: number) => void
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
      setActive({ scenario, from: sessionRef, base: null, started: false })
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

  const turns = active?.scenario.turns ?? []
  const { got, off } = active && active.base !== null ? progress(entries.slice(active.base), turns) : { got: [] as string[], off: false }
  const next = got.length

  // The new session is the scenario's: from then on its replies are the steps' answers.
  useEffect(() => {
    setActive((a) => (a && a.base === null && sessionRef !== a.from ? { ...a, base: entries.length } : a))
  }, [sessionRef, entries.length])

  // On a phone the drawer covers the chat: once a message is sent it closes, and the focus goes to the chat's input (the drawer's
  // own close would give it back to the button that opened it, and that comes a render later).
  const backToChat = useCallback(() => {
    onClose()
    requestAnimationFrame(() => document.getElementById('composer-input')?.focus())
  }, [onClose])

  // The scenario's first message is sent as soon as its session is up.
  useEffect(() => {
    if (!active || active.base === null || active.started || pending || turns.length === 0) return
    setActive({ ...active, started: true })
    void send(turns[0])
    if (overlay) backToChat()
  }, [active, pending, turns, send, overlay, backToChat])

  // The message of the step in course that is already in the chat and has no answer: what became of it says what the button does.
  // One that did not go through (failed, or lost its answer) is retried, with its own key: a new send would be a second message,
  // and the API may already have the first. One the API has, or one on its way, is not sent again; the chat's bubble says so.
  const mine = active && active.base !== null ? entries.slice(active.base) : []
  const stepText = turns[next]?.trim()
  const stepEntry = stepText === undefined ? undefined : [...mine].reverse().find((e): e is UserEntry =>
    e.role === 'user' && e.text.trim() === stepText && !mine.some((a) => a.role === 'assistant' && a.to === e.id))
  const stepState = !stepEntry ? 'new' : stepEntry.delivery === 'failed' || stepEntry.delivery === 'uncertain' ? 'retry' : 'held'

  function sendStep() {
    if (stepEntry && stepState === 'retry') retry(stepEntry.id)
    else if (stepState === 'new') void send(turns[next])
    else return
    if (overlay) backToChat()
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
              <article
                key={s.id}
                className="demo__card"
                aria-label={text(s.title)}
                tabIndex={active?.scenario.id === s.id ? -1 : undefined}
                data-active-scenario={active?.scenario.id === s.id ? '' : undefined}
              >
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
                            {active.base !== null && i === next && (
                              <Button variant="ghost" size="sm" tinted disabled={pending || ended || stepState === 'held'} onClick={sendStep}>
                                {t(stepState === 'retry' ? 'demo.steps.retry' : 'demo.steps.send', { n: i + 1 })}
                              </Button>
                            )}
                            {active.base !== null && i === next && stepEntry?.delivery === 'processed' && <span className="demo__muted">{t('demo.steps.processed')}</span>}
                          </li>
                        )
                      })}
                    </ol>
                    {off && <p className="demo__note" role="status">{t('demo.steps.offScript')}</p>}
                    <div className="demo__actions">
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
