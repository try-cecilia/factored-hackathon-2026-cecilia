import { useCallback, useEffect, useRef, useState } from 'react'
import { loadNamespaces } from '../i18n/areas'
import { useI18n, useT } from '../i18n/context'
import { translator, type Dictionary, type MessageKey, type Translate } from '../i18n/translate'
import { applyDemoFault, getDemoTickets, startScenario } from '../server/demo.functions'
import { nextStepText, questionTexts, reasonText } from '../routes/-operator/notes'
import { Button, IconButton } from '../ui'
import { priorityOf } from '../ui/table/priority'
import type { Entry, UserEntry } from './conversation'
import { newMessageKey } from './key'
import type { DemoFault, DemoScenario, DemoTicket } from './types'
import './DemoPanel.css'

/**
 * The scenario in course. `from` is the session it was chosen in: the new one is there when `sessionRef` differs, and `base` is
 * how many entries that conversation already had. `steps` is the panel's own record of what it sent, by step: the message's key
 * (the one the API deduplicates by) and, once its reply came, the disposition. The conversation is bounded and is read again
 * (its history keeps the last 40 entries, without keys), so the progress is never rebuilt from it: a step that was sent is not
 * offered again as new, however the conversation was reloaded.
 */
type StepRecord = { key: string; disposition: string | null }
type Active = { scenario: DemoScenario; from: string; base: number | null; steps: StepRecord[] }

const PATHS = ['normal', 'ambiguous', 'out_of_scope', 'action', 'human', 'attack', 'failure'] as const
const DISPOSITIONS = ['AUTO_RESOLVE', 'CLARIFY', 'ABSTAIN', 'ESCALATE'] as const
const FAULTS = ['llm_outage', 'expire_session', 'clear_traces'] as const

function known<T extends string>(list: readonly T[], value: string): value is T {
  return (list as readonly string[]).includes(value)
}

// DEMO_MODE only. Everything here talks to the API's /demo endpoints through the server; the customer app works
// the same without it, and it is drawn apart, on its own panel with its own label, so nobody mistakes it for the service.
// A scenario sends its messages through the chat's own send, like any suggestion: the first one when its session is up, the
// next ones with the button of the step in course. Each message goes with a key the panel keeps, so a reply is the step's when
// it answers the message with that key; a reply to any other message (one the person wrote by hand) is not a step (the card says
// so), so an unrelated message does not move the scenario. Each reply says which message it answers (`to`), because a retry's
// reply comes late, after other messages.

export function DemoPanel({ scenarios, sessionRef, entries, pending, escalations, ended, send, onSend, retry, overlay, onSessionChanged, onClose }: {
  scenarios: DemoScenario[]
  sessionRef: string
  entries: Entry[]
  pending: boolean
  escalations: number
  /** The session is over: no step can be sent (loading a scenario starts another). */
  ended: boolean
  /** The chat's own send: the messages of a scenario go through it, with the same key, the same state and the same retry. */
  send: (text: string, key?: string) => Promise<unknown>
  /** Tells the panel each message the chat sends and its key, so a step sent from anywhere is the step. */
  onSend: (listener: (sent: { text: string; key: string }) => void) => () => void
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
  // The bank view reads the ticket as the operator's console does, with the console's texts: the customer's page does not carry them
  // (areas.ts), so the panel, which only exists in the demo, asks for the ones it needs when it is drawn, in the language it is in.
  const [desk, setDesk] = useState<{ locale: string; t: Translate } | null>(null)
  useEffect(() => {
    let current = true
    void loadNamespaces(['table', 'operator'], locale).then((messages: Dictionary) => { if (current) setDesk({ locale, t: translator(messages) }) })
    return () => { current = false }
  }, [locale])
  const deskT = desk?.locale === locale ? desk.t : null

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
      setActive({ scenario, from: sessionRef, base: null, steps: [] })
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
  const steps = active?.steps ?? []
  let next = 0
  while (steps[next]?.disposition) next++
  const got = steps.slice(0, next).map((r) => r.disposition as string)
  // A reply that is not to a step's message: the last one, when it is to a message written by hand (one with a key that is not a step's).
  const lastReply = [...entries].reverse().find((e) => e.role === 'assistant')
  const asked = lastReply?.role === 'assistant' && lastReply.to !== undefined ? entries.find((e) => e.role === 'user' && e.id === lastReply.to) : undefined
  const off = !!active && active.base !== null && asked?.role === 'user' && asked.key !== null && !steps.some((r) => r.key === asked.key)

  // The new session is the scenario's: from then on its replies are the steps' answers.
  useEffect(() => {
    setActive((a) => (a && a.base === null && sessionRef !== a.from ? { ...a, base: entries.length } : a))
  }, [sessionRef, entries.length])

  // A step is answered when the reply to its message (found by key) comes; the disposition is kept, so a reload that drops it
  // from the conversation does not take the progress with it.
  useEffect(() => {
    if (!active || active.base === null) return
    const answered = new Map<number, string>()
    active.steps.forEach((r, i) => {
      if (r.disposition) return
      const user = entries.find((e): e is UserEntry => e.role === 'user' && e.key === r.key)
      const reply = user && entries.find((e) => e.role === 'assistant' && e.to === user.id)
      if (reply?.role === 'assistant') answered.set(i, reply.reply.disposition)
    })
    if (answered.size === 0) return
    setActive((a) => a && { ...a, steps: a.steps.map((r, i) => (answered.has(i) ? { ...r, disposition: answered.get(i) as string } : r)) })
  }, [active, entries])

  // A message sent from anywhere (the composer, a suggestion, a bubble's button) whose text is the step in course is that step: it
  // is recorded with its real key, so the card does not offer it again as new and its retries go with that key. A step that
  // already has its record is not changed by another message of the same text.
  useEffect(() => onSend(({ text, key }) => {
    setActive((a) => {
      if (!a || a.base === null) return a
      let n = 0
      while (a.steps[n]?.disposition) n++
      const turn = a.scenario.turns[n]
      if (a.steps[n] || turn === undefined || turn.trim() !== text.trim()) return a
      return { ...a, steps: [...a.steps.slice(0, n), { key, disposition: null }] }
    })
  }), [onSend])

  // On a phone the drawer covers the chat: once a message is sent it closes, and the focus goes to the chat's input (the drawer's
  // own close would give it back to the button that opened it, and that comes a render later).
  const backToChat = useCallback(() => {
    onClose()
    requestAnimationFrame(() => document.getElementById('composer-input')?.focus())
  }, [onClose])

  const start = useCallback((step: number, key: string) => {
    setActive((a) => a && { ...a, steps: [...a.steps.slice(0, step), { key, disposition: null }] })
    void send(active?.scenario.turns[step] ?? '', key)
  }, [send, active?.scenario])

  // The scenario's first message is sent as soon as its session is up (once per scenario in course, also with effects run twice).
  const first = useRef<Active | null>(null)
  useEffect(() => {
    if (!active || active.base === null || active.steps.length > 0 || pending || turns.length === 0 || first.current === active) return
    first.current = active
    start(0, newMessageKey())
    if (overlay) backToChat()
  }, [active, pending, turns, start, overlay, backToChat])

  // The message of the step in course, by its key, says what the button does. One that did not go through (failed, or lost its
  // answer) is retried with its own key: a new key would be a second message, and the API may already have the first. If it is no
  // longer in the conversation (a reload dropped it) it is sent again with the same key, which the API answers once. One the API
  // has, or one on its way, is not sent again; the chat's bubble says so. Only a step never sent goes with a new key.
  const record = steps[next]
  const stepEntry = record ? entries.find((e): e is UserEntry => e.role === 'user' && e.key === record.key) : undefined
  const stepState = !record ? 'new' : !stepEntry ? 'resend' : stepEntry.delivery === 'failed' || stepEntry.delivery === 'uncertain' ? 'retry' : 'held'

  function sendStep() {
    if (stepState === 'new') start(next, newMessageKey())
    else if (stepState === 'retry' && stepEntry) retry(stepEntry.id)
    else if (stepState === 'resend' && record) void send(turns[next], record.key)
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
                                {t(stepState === 'retry' || stepState === 'resend' ? 'demo.steps.retry' : 'demo.steps.send', { n: i + 1 })}
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
        ) : !deskT ? null : (
          tickets.map((ticket) => (
            <article key={ticket.ticket_id} className="demo__card">
              <div className="demo__row">
                <code>{ticket.queue}</code>
                <span className="demo__tag">{deskT(`table.priority.${priorityOf(ticket.priority)}`)}</span>
              </div>
              <dl className="demo__facts">
                <dt>{t('demo.bank.request')}</dt><dd>{ticket.request}</dd>
                <dt>{t('demo.bank.reason')}</dt><dd>{reasonText(deskT, ticket)}</dd>
                {ticket.open_questions.length > 0 && <><dt>{t('demo.bank.questions')}</dt><dd>{questionTexts(deskT, ticket).join(' · ')}</dd></>}
                <dt>{t('demo.bank.next')}</dt><dd>{nextStepText(deskT, ticket)}</dd>
              </dl>
              <code className="demo__muted">{ticket.ticket_id}</code>
            </article>
          ))
        )}
      </section>
    </aside>
  )
}
