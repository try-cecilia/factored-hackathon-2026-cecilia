import { useState, type ReactNode } from 'react'
import { useI18n, useT } from '../../i18n/context'
import type { MessageKey } from '../../i18n/translate'
import type { DeskAction, DeskState, Result, Ticket } from '../../server/operator.functions'
import { Button, IconButton, PriorityChip, priorityOf, StatusIndicator, type StatusTone } from '../../ui'
import { AlertCircleIcon, AlertTriangleIcon, CheckIcon, InfoCircleIcon } from '../../ui/messages/icons'
import { CloseIcon } from '../../ui/table/icons'
import { ago, clock, CLOSED, explainKey, money, shortStamp, when } from './format'
import { FRAUD_SCORE_FLAG, behaviorOf, isFlagged, resolutionMessage, scoreLabel, ticketSummary } from './summary'
import { conflictOf, holdConflict, type Conflict } from './conflicts'
import { evidenceTypeName, keyName, nextStepText, questionTexts, reasonText, reviewReasonName, ruleName } from './notes'
import { KeyValues } from './ui'

export type TicketPanelProps = {
  ticket: Ticket
  /** Who is looking: `canAct` is a session with an operator key, and `operator` is the name that key carries. */
  view: { canAct: boolean; operator: string | null }
  /** Sends one action. The panel always passes the version it is showing. */
  act: (action: DeskAction, input: { expectedVersion: number; reason?: string; message?: string }) => Promise<Result<DeskState>>
  /** Reads the ticket again from the server. `true` only when the case was read and is now on screen. */
  reload: (minVersion: number) => Promise<boolean>
  /** Status of the last read of this case when it failed: the panel keeps what it has and says it is not fresh. */
  loadError?: number
  /** Close button of the header. Left out where there is nothing to close (small screens show a back link instead). */
  onClose?: () => void
  /** Read-only sessions: the form that adds an operator key. It posts natively, so it comes from outside. */
  keyForm?: ReactNode
  /** Link to the trace of the turn that filed the case. */
  traceLink?: ReactNode
}

type Flash = { tone: 'ok' | 'error'; title?: string; text: string; detail?: string }

// The API's limit for the message a resolution leaves the customer.
const MESSAGE_MAX = 500

const tones: Record<DeskState['status'], StatusTone> = { open: 'open', claimed: 'info', approved: 'success', rejected: 'danger', handed_back: 'neutral', stale: 'caution', resolved: 'success' }

/** The ticket desk of the operator console: what the case is, what the assistant did, and what the operator can do next. */
export function TicketPanel({ ticket, view, act, reload, loadError, onClose, keyForm, traceLink }: TicketPanelProps) {
  const t = useT()
  const { locale } = useI18n()
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState<DeskAction | 'reload' | null>(null)
  const [flash, setFlash] = useState<Flash | null>(null)
  const [conflict, setConflictNow] = useState<Conflict | null>(() => conflictOf(ticket.ticket_id))
  const setConflict = (next: Conflict | null) => {
    holdConflict(ticket.ticket_id, next)
    setConflictNow(next)
  }
  const [copied, setCopied] = useState<'ok' | 'error' | null>(null)
  const [reloadFailed, setReloadFailed] = useState(false)

  const { desk } = ticket
  const closed = CLOSED.includes(desk.status)
  const mine = view.canAct && view.operator !== null && desk.status === 'claimed' && desk.operator === view.operator
  // After a 409 the screen already shows the current state, but nothing can be decided until the operator has read the notice.
  const locked = conflict !== null
  const busy = pending !== null
  const evidence = ticket.evidence.filter((e) => e.type === 'transaction')
  const otherEvidence = ticket.evidence.filter((e) => e.type !== 'transaction')
  const flagged = evidence.filter(isFlagged).length
  const last = desk.history.at(-1)

  async function run(action: DeskAction) {
    setPending(action)
    setFlash(null)
    try {
      const result = await act(action, {
        expectedVersion: desk.version,
        reason: action === 'reject' ? reason.trim() || undefined : undefined,
        message: action === 'resolve' ? message.trim() : undefined,
      })
      if (result.ok) {
        setConflict(null)
        setReason('')
        setMessage('')
        setFlash({ tone: 'ok', text: t(`operator.ticket.result.${action}` as MessageKey) })
      } else if (result.status === 409) {
        setConflict({ seen: desk.version, detail: result.message })
      } else {
        setFlash({ tone: 'error', text: t(explainKey(result.status, true)), detail: result.status === 400 ? result.message : undefined })
      }
      // Whatever happened the case is read again: after a 409 the screen was out of date.
      await reload(desk.version)
    } catch {
      setFlash({ tone: 'error', text: t('operator.errors.actionFailed') })
    }
    setPending(null)
  }

  // The lock of a 409 is lifted only by a reload that worked: with the case not read again, what is on screen may still be stale.
  async function reloadNow() {
    setPending('reload')
    const fresh = await reload(desk.version).catch(() => false)
    if (fresh) setConflict(null)
    setReloadFailed(!fresh)
    setPending(null)
  }

  async function copySummary() {
    try {
      await navigator.clipboard.writeText(ticketSummary(ticket, t))
      setCopied('ok')
    } catch {
      setCopied('error')
    }
    setTimeout(() => setCopied(null), 2500)
  }

  const who = desk.operator ?? ''
  const state =
    desk.status === 'open' ? t('operator.ticket.state.unassigned')
    : desk.status === 'claimed' ? (mine ? t('operator.ticket.state.claimedByYou') : t('operator.ticket.state.claimedBy', { name: who }))
    : t(`operator.ticket.state.${{ approved: 'approvedBy', rejected: 'rejectedBy', handed_back: 'handedBackBy', stale: 'staleBy', resolved: 'resolvedBy' }[desk.status]}` as MessageKey, { name: last?.operator ?? who })

  const pendingAction = ticket.pending_action
  // A case that carries an action closes by approving or rejecting that action; any other one, by resolving it with a message.
  const decisions: readonly DeskAction[] = pendingAction ? ['approve', 'reject'] : ['resolve']
  // Who may write in the box of a decision, said in its placeholder.
  const hint = (box: 'reason' | 'message') =>
    !view.canAct ? t('operator.ticket.footer.readOnly')
    : desk.status === 'open' ? t(`operator.ticket.${box}.unassigned`)
    : mine ? t(`operator.ticket.${box}.placeholder`)
    : t(`operator.ticket.${box}.lockedBy`, { name: who })

  return (
    <article className="op-ticket" aria-labelledby="op-ticket-title" data-state={desk.status}>
      <header className="op-ticket__head">
        <div className="op-ticket__id">
          <h1 id="op-ticket-title" className="op-mono">{ticket.ticket_id.slice(0, 8)}</h1>
          <PriorityChip priority={priorityOf(ticket.priority)} />
          <span className="op-mono op-muted">{ticket.queue}</span>
          <span className="op-head__spacer" />
          {conflict ? (
            <span className="op-version op-version--conflict" aria-label={t('operator.ticket.versionChangeLabel', { from: conflict.seen, to: desk.version })}>
              {t('operator.ticket.versionChange', { from: conflict.seen, to: desk.version })}
            </span>
          ) : (
            <span className="op-version" aria-label={t('operator.ticket.versionLabel', { n: desk.version })}>{t('operator.ticket.version', { n: desk.version })}</span>
          )}
          {onClose && <IconButton variant="ghost" size="xs" label={t('operator.ticket.close')} icon={<CloseIcon size={12} />} onClick={onClose} />}
        </div>
        <p className="op-ticket__state">
          <StatusIndicator tone={tones[desk.status]}><strong>{state}</strong></StatusIndicator>
          <span className="op-muted">
            {t('operator.ticket.meta', { age: ago(ticket.created_at, locale) })}
            {[ticket.country, ticket.language ? ticket.language.toUpperCase() : t('operator.queue.unknownLanguage'), ticket.segment].filter(Boolean).map((part) => ` · ${part}`)}
          </span>
        </p>
      </header>

      <div className="op-ticket__body">
        <div aria-live="polite">
          {(reloadFailed || loadError !== undefined) && (
            <Banner tone="danger" title={t('operator.ticket.banner.reloadFailedTitle')}>
              {loadError !== undefined ? t(explainKey(loadError)) : t('operator.ticket.banner.reloadFailedBody')}
            </Banner>
          )}
          {conflict && <ConflictBanner conflict={conflict} ticket={ticket} />}
          {!conflict && flash && flash.tone === 'error' && <Banner tone="danger" title={t('operator.ticket.banner.errorTitle')}>{flash.text}{flash.detail ? ` (${flash.detail})` : ''}</Banner>}
          {!conflict && flash?.tone === 'ok' && !closed && <Banner tone="info">{flash.text}</Banner>}
          {!conflict && closed && <OutcomeBanner ticket={ticket} />}
        </div>

        <section className="op-block" aria-label={t('operator.ticket.request')}>
          <h2>{t('operator.ticket.request')}</h2>
          <p className="op-request">{ticket.request}</p>
          <p className="op-muted">{t('operator.ticket.reasonLine', { reason: reasonText(t, ticket), rule: ruleName(t, ticket.policy_rule) })}</p>
          {ticket.prior_requests.length > 0 && (
            <>
              <h3>{t('operator.ticket.priorRequests')}</h3>
              <ul className="op-plain">{ticket.prior_requests.map((p, i) => <li key={i}>{p}</li>)}</ul>
            </>
          )}
        </section>

        {pendingAction && <PendingCard ticket={ticket} />}

        {!closed && pendingAction && (
          <section className="op-block">
            <label htmlFor="op-reason"><h2>{t('operator.ticket.reason.label')}</h2></label>
            <textarea
              id="op-reason"
              className="op-input op-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={300}
              rows={2}
              disabled={!mine || locked}
              placeholder={hint('reason')}
            />
          </section>
        )}

        {!closed && !pendingAction && (
          <section className="op-block">
            <div className="op-block__head">
              <label htmlFor="op-message"><h2>{t('operator.ticket.message.label')}</h2></label>
              <span id="op-message-count" className="op-mono op-muted">{`${message.length}/${MESSAGE_MAX}`}</span>
            </div>
            <textarea
              id="op-message"
              className="op-input"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={MESSAGE_MAX}
              rows={3}
              disabled={!mine || locked}
              placeholder={hint('message')}
              aria-describedby="op-message-count"
            />
          </section>
        )}

        {ticket.evidence.length > 0 ? (
          <section className="op-block" aria-label={t('operator.ticket.evidence.title')}>
            <div className="op-block__head">
              <h2>{t('operator.ticket.evidence.title')}</h2>
              <span className={flagged ? 'op-flagged-count' : 'op-muted'}>
                {flagged ? t('operator.ticket.evidence.flagged', { count: flagged, threshold: FRAUD_SCORE_FLAG }) : t('operator.ticket.evidence.count', { count: ticket.evidence.length })}
              </span>
            </div>
            {evidence.length > 0 && (
              <table className="op-ev">
                <caption className="sr-only">{t('operator.ticket.evidence.caption')}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t('operator.ticket.evidence.date')}</th>
                    <th scope="col" className="op-ev__end">{t('operator.ticket.evidence.amount')}</th>
                    <th scope="col">{t('operator.ticket.evidence.merchant')}</th>
                    <th scope="col" className="op-ev__end">{t('operator.ticket.evidence.score')}</th>
                    <th scope="col" className="op-ev__end">{t('operator.ticket.evidence.behavior')}</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.map((e) => (
                    <tr key={e.id ?? shortStamp(e.detail.transaction_date)} data-flagged={isFlagged(e) ? '' : undefined}>
                      <td className="op-mono" title={e.id ?? undefined}>{shortStamp(e.detail.transaction_date)}</td>
                      <td className="op-mono op-ev__end">{money(e.detail.amount, e.detail.currency)}</td>
                      <td>{[e.detail.merchant_name, e.detail.transaction_country].filter(Boolean).map(String).join(' · ') || '—'}</td>
                      <td className="op-mono op-ev__end">
                        {isFlagged(e) && (
                          <>
                            <svg className="op-flag" viewBox="0 0 20 20" width="10" height="10" aria-hidden="true" focusable="false"><path d="M5 17V3.5M5 4h9l-2 3.5L14 11H5" fill="currentColor" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" /></svg>
                            <span className="sr-only">{t('operator.ticket.evidence.flag', { score: scoreLabel(e) })}</span>
                          </>
                        )}
                        <span aria-hidden={isFlagged(e) || undefined}>{scoreLabel(e)}</span>
                      </td>
                      <td className="op-mono op-ev__end">
                        {(() => {
                          const b = behaviorOf(e)
                          return b ? `${Math.round(b.composite)} · ${t(`operator.ticket.evidence.band.${b.band}`)}` : <span title={t('operator.ticket.evidence.behaviorNone')}>—</span>
                        })()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {evidence.length > 0 && <p className="op-muted">{t('operator.ticket.evidence.behaviorNote')}</p>}
            {otherEvidence.map((e, i) => (
              <div key={i}>
                <h3>{evidenceTypeName(t, e.type)}{e.id ? ` · ${e.id}` : ''}</h3>
                <KeyValues data={e.detail} label={(key) => keyName(t, key)} />
              </div>
            ))}
          </section>
        ) : null}

        {ticket.verified_facts.length > 0 && (
          <section className="op-block">
            <h2>{t('operator.ticket.verifiedFacts')}</h2>
            <ul className="op-facts">
              {ticket.verified_facts.map((fact, i) => (
                <li key={i}>
                  <CheckIcon size={10} />
                  <span className="op-mono">{Object.entries(fact).map(([k, v]) => `${keyName(t, k)}: ${typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}`).join(' · ')}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {ticket.open_questions.length > 0 && (
          <section className="op-block">
            <h2>{t('operator.ticket.openQuestions')}</h2>
            <ul className="op-bullets">{questionTexts(t, ticket).map((q, i) => <li key={i}>{q}</li>)}</ul>
          </section>
        )}

        <section className="op-block">
          <h2>{t('operator.ticket.nextStep')}</h2>
          <p className="op-callout">{nextStepText(t, ticket)}</p>
        </section>

        {ticket.actions_taken.length > 0 && (
          <section className="op-block">
            <h2>{t('operator.ticket.actionsTaken')}</h2>
            <ul className="op-facts">
              {ticket.actions_taken.map((a, i) => (
                <li key={i}><span className="op-mono">{String(a.tool ?? a.tool_name ?? '—')}{a.error_type ? ` · ${String(a.error_type)}` : ''}</span></li>
              ))}
            </ul>
          </section>
        )}

        <section className="op-block">
          <h2>{t('operator.ticket.history')}</h2>
          <ol className="op-history">
            {[...desk.history].reverse().map((h, i, all) => {
              const version = all.length - i
              const name = h.operator
              const text =
                h.status === 'claimed' ? t('operator.ticket.historyItem.claim', { name })
                : h.status === 'approved' ? t('operator.ticket.historyItem.approve', { name })
                : h.status === 'rejected' ? t('operator.ticket.historyItem.reject', { name })
                : h.status === 'handed_back' ? t('operator.ticket.historyItem.release', { name })
                : h.status === 'stale' ? t('operator.ticket.state.staleBy', { name })
                : h.status === 'resolved' ? t('operator.ticket.historyItem.resolve', { name })
                : t('operator.ticket.historyItem.other', { action: h.action, name })
              // A rejection carries the operator's internal reason; a resolution, the message the customer got.
              const said = h.detail.reason || h.detail.message
              const quoted = typeof said === 'string' && said ? said : null
              return (
                <li key={i}>
                  <StatusIndicator tone={tones[h.status as DeskState['status']] ?? 'neutral'}>
                    <span>{text}{quoted && <em className="op-muted"> — “{quoted}”</em>}</span>
                  </StatusIndicator>
                  <span className={conflict && version === desk.version && version !== conflict.seen ? 'op-mono op-danger' : 'op-mono op-muted'} title={when(h.ts, locale)}>
                    {t('operator.ticket.versionAge', { n: version, age: ago(h.ts, locale) })}
                  </span>
                </li>
              )
            })}
            <li>
              <StatusIndicator tone="open"><span>{t('operator.ticket.historyFiled')}</span></StatusIndicator>
              <span className="op-mono op-muted" title={when(ticket.created_at, locale)}>{ago(ticket.created_at, locale)}</span>
            </li>
          </ol>
          <p className="op-ids op-mono op-muted">
            {ticket.trace_id && (traceLink ?? <span>{t('operator.ticket.trace', { id: ticket.trace_id.slice(0, 8) })}</span>)}
            <span>{t('operator.ticket.session', { id: ticket.session_ref.slice(0, 8) })}</span>
          </p>
        </section>
      </div>

      <footer className="op-ticket__foot">
        {!view.canAct && !closed && (
          <div className="op-needkey">
            <p>{t('operator.ticket.needKey')}</p>
            {keyForm}
          </div>
        )}
        <div className="op-actions" role="group" aria-label={t('operator.ticket.panelLabel')}>
          {conflict && (
            <>
              <Button size="sm" onClick={() => void reloadNow()} loading={pending === 'reload'}>{t('operator.ticket.actions.reload')}</Button>
              {(desk.status === 'open' ? (['claim'] as const) : mine ? decisions : []).map((a) => (
                <Button key={a} size="sm" variant="ghost" tinted disabled>{t(`operator.ticket.actions.${a}` as MessageKey)}</Button>
              ))}
            </>
          )}
          {!conflict && closed && <span className="op-muted op-actions__note">{t('operator.ticket.footer.closed')}</span>}
          {!conflict && !closed && !view.canAct && <span className="op-muted op-actions__note">{t('operator.ticket.footer.readOnly')}</span>}
          {!conflict && !closed && view.canAct && desk.status === 'open' && (
            <>
              <span className="op-muted op-actions__note">{t('operator.ticket.footer.notAssigned')}</span>
              <Button size="sm" onClick={() => void run('claim')} loading={pending === 'claim'} disabled={busy}>{pending === 'claim' ? t('operator.ticket.actions.sending.claim') : t('operator.ticket.actions.claim')}</Button>
            </>
          )}
          {!conflict && !closed && view.canAct && desk.status === 'claimed' && !mine && (
            <span className="op-muted op-actions__note">{t('operator.ticket.footer.claimedByOther', { name: who })}</span>
          )}
          {!conflict && mine && (
            <>
              {pendingAction ? (
                <>
                  <Button size="sm" onClick={() => void run('approve')} loading={pending === 'approve'} disabled={busy}>{pending === 'approve' ? t('operator.ticket.actions.sending.approve') : t('operator.ticket.actions.approve')}</Button>
                  <Button size="sm" variant="ghost" tinted onClick={() => void run('reject')} loading={pending === 'reject'} disabled={busy}>{pending === 'reject' ? t('operator.ticket.actions.sending.reject') : t('operator.ticket.actions.reject')}</Button>
                </>
              ) : (
                <Button size="sm" onClick={() => void run('resolve')} loading={pending === 'resolve'} disabled={busy || !message.trim()}>{pending === 'resolve' ? t('operator.ticket.actions.sending.resolve') : t('operator.ticket.actions.resolve')}</Button>
              )}
              <span className="op-head__spacer" />
              <Button size="sm" variant="ghost" muted onClick={() => void run('release')} loading={pending === 'release'} disabled={busy}>{pending === 'release' ? t('operator.ticket.actions.sending.release') : t('operator.ticket.actions.release')}</Button>
            </>
          )}
        </div>
        {(mine || closed) && (
          <div className="op-audit">
            <span className="op-muted">{mine && view.operator ? t('operator.ticket.footer.auditedAs', { name: view.operator }) : ''}</span>
            <Button variant="ghost" size="sm" muted onClick={() => void copySummary()}>{t('operator.ticket.actions.copy')}</Button>
            <span className="sr-only" role="status">{copied === 'ok' ? t('operator.ticket.actions.copied') : copied === 'error' ? t('operator.ticket.actions.copyFailed') : ''}</span>
            {copied && <span className="op-copied" aria-hidden="true">{copied === 'ok' ? t('operator.ticket.actions.copied') : t('operator.ticket.actions.copyFailed')}</span>}
          </div>
        )}
      </footer>
    </article>
  )
}

function Banner({ tone, title, children }: { tone: 'danger' | 'success' | 'info' | 'caution' | 'neutral'; title?: string; children?: ReactNode }) {
  const Icon = tone === 'danger' ? AlertCircleIcon : tone === 'caution' ? AlertTriangleIcon : tone === 'success' ? CheckIcon : InfoCircleIcon
  return (
    <div className={`op-banner op-banner--${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon size={14} />
      <div>
        {title && <strong>{title}</strong>}
        {children && <p>{children}</p>}
      </div>
    </div>
  )
}

/** "You decided on v3. It is now v4: diego.m released it to the assistant at 10:42." — from the ticket as the server holds it now. */
function ConflictBanner({ conflict, ticket }: { conflict: Conflict; ticket: Ticket }) {
  const t = useT()
  const { locale } = useI18n()
  const { desk } = ticket
  const last = desk.history.at(-1)
  const moved = desk.version !== conflict.seen && last
  const what = last ? t(`operator.ticket.banner.conflictWhat.${(['claim', 'approve', 'reject', 'release', 'resolve'] as const).includes(last.action as never) ? last.action : 'other'}` as MessageKey) : ''
  return (
    <Banner tone="danger" title={t('operator.ticket.banner.conflictTitle')}>
      {moved ? t('operator.ticket.banner.conflictBody', { seen: conflict.seen, now: desk.version, who: last.operator, what, time: clock(last.ts, locale) }) : t('operator.ticket.banner.conflictGeneric')}
      {conflict.detail ? <span className="op-mono op-banner__detail">{conflict.detail}</span> : null}
    </Banner>
  )
}

function OutcomeBanner({ ticket }: { ticket: Ticket }) {
  const t = useT()
  const { status, trace_id } = ticket.desk
  const message = resolutionMessage(ticket.desk)
  if (status === 'approved') return <Banner tone="success" title={t('operator.ticket.banner.traceOpened')}>{trace_id ? t('operator.ticket.banner.traceOpenedBody', { id: trace_id }) : undefined}</Banner>
  if (status === 'resolved') return <Banner tone="success" title={t('operator.ticket.banner.resolvedTitle')}>{message ? t('operator.ticket.banner.resolvedBody', { message }) : undefined}</Banner>
  if (status === 'stale') return <Banner tone="caution" title={t('operator.ticket.banner.staleTitle')}>{t('operator.ticket.banner.staleBody')}</Banner>
  if (status === 'rejected') return <Banner tone="neutral" title={t('operator.ticket.banner.rejectedTitle')}>{t('operator.ticket.banner.rejectedBody')}</Banner>
  return <Banner tone="neutral" title={t('operator.ticket.banner.handedBackTitle')}>{t('operator.ticket.banner.handedBackBody')}</Banner>
}

/** The action the assistant cannot take alone, as a white card of definitions. */
function PendingCard({ ticket }: { ticket: Ticket }) {
  const t = useT()
  const p = ticket.pending_action!
  const { status } = ticket.desk
  const rejectedWith = [...ticket.desk.history].reverse().find((h) => h.status === 'rejected')?.detail.reason
  const badge =
    status === 'approved' ? { key: 'operator.ticket.pending.approved', tone: 'success' }
    : status === 'rejected' ? { key: 'operator.ticket.pending.rejected', tone: 'danger' }
    : status === 'stale' ? { key: 'operator.ticket.pending.stale', tone: 'caution' }
    : status === 'handed_back' ? { key: 'operator.ticket.pending.handedBack', tone: 'neutral' }
    : { key: 'operator.ticket.pending.needsDecision', tone: 'caution' }
  const rows: [string, ReactNode][] = [
    [t('operator.ticket.pending.movement'), <span className="op-mono">{p.transaction_id}</span>],
    [t('operator.ticket.pending.product'), <span className="op-mono">{p.product_id}</span>],
    [t('operator.ticket.pending.amount'), <span className="op-mono op-strong">{p.movement ? money(p.movement.amount, p.movement.currency) : '—'}</span>],
    ...(p.age_days != null ? [[t('operator.ticket.pending.date'), t('operator.ticket.pending.dateValue', { days: p.age_days })] as [string, ReactNode]] : []),
    ...(p.review_reason ? [[t('operator.ticket.pending.reviewReason'), <span title={p.review_reason}>{reviewReasonName(t, p.review_reason)}</span>] as [string, ReactNode]] : []),
    ...(!CLOSED.includes(status) ? [[t('operator.ticket.pending.ifApproved'), t('operator.ticket.pending.ifApprovedValue')] as [string, ReactNode]] : []),
    ...(typeof rejectedWith === 'string' && rejectedWith ? [[t('operator.ticket.pending.reasonGiven'), rejectedWith] as [string, ReactNode]] : []),
  ]
  return (
    <section className="op-card" aria-label={t('operator.ticket.pending.title')}>
      <header>
        <h2>{t('operator.ticket.pending.title')}</h2>
        <span className={`op-tag op-tag--${badge.tone}`}>{t(badge.key as MessageKey)}</span>
      </header>
      <dl>
        {rows.map(([name, value]) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

