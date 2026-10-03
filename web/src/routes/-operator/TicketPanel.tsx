import { useState, type ReactNode } from 'react'
import { useI18n, useT } from '../../i18n/context'
import type { MessageKey } from '../../i18n/translate'
import type { CustomerContext } from '../../server/customer-context'
import type { DeskAction, DeskState, Result, Ticket } from '../../server/operator.functions'
import { Button, IconButton, PriorityChip, priorityOf, StatusIndicator, type StatusTone } from '../../ui'
import { AlertCircleIcon, AlertTriangleIcon, CheckIcon, InfoCircleIcon } from '../../ui/messages/icons'
import { CloseIcon } from '../../ui/table/icons'
import { ago, clock, CLOSED, explainKey, money, shortStamp, when } from './format'
import { FRAUD_SCORE_FLAG, behaviorOf, isFlagged, resolutionMessage, scoreLabel, ticketSummary } from './summary'
import { conflictOf, holdConflict, type Conflict } from './conflicts'
import { segmentName } from './context'
import { evidenceTypeName, keyName, nextStepText, questionTexts, reasonText, reviewReasonName, ruleName } from './notes'
import { KeyValues } from './ui'
import { Attention } from './Attention'
import { CasesFold, ContextNotice, MovementsFold, ProductsFold, TracesFold, useCustomerContext, type CaseLink } from './CustomerContext'
import { Fold, FoldGroup } from './Folds'

export type TicketPanelProps = {
  ticket: Ticket
  /** Who is looking: `canAct` is a session with an operator key, and `operator` is the name that key carries. */
  view: { canAct: boolean; operator: string | null }
  /** Sends one action. The panel always passes the version it is showing. */
  act: (action: DeskAction, input: { expectedVersion: number; reason?: string; message?: string; resultCode?: string }) => Promise<Result<DeskState>>
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
  /** Reads the customer's context of this case (on its own, so the case never waits for it: see CustomerContext.tsx). Left out, the panel shows no customer. */
  loadContext?: (ticketId: string) => Promise<Result<CustomerContext>>
  /** Wraps the label of another case of the customer in the link that opens it. Left out, the id is plain text. */
  caseLink?: CaseLink
  /**
   * The predefined results the case may be resolved with (the demo's bank side). Given, resolving takes one of them, required, and
   * the message becomes optional: the customer reads it after the result. Left out, the console's free message, required, as always.
   */
  resolveOptions?: { code: string; label: string }[]
  /** What the footer says of the person who holds the case, in place of "audited as {name}". */
  auditNote?: string
}

type Flash = { tone: 'ok' | 'error'; title?: string; text: string; detail?: string }

const merchantOf = (e: Ticket['evidence'][number]) => [e.detail.merchant_name, e.detail.transaction_country].filter(Boolean).map(String).join(' · ')

// The API's limit for the message a resolution leaves the customer.
const MESSAGE_MAX = 500

const tones: Record<DeskState['status'], StatusTone> = { open: 'open', claimed: 'info', approved: 'success', rejected: 'danger', handed_back: 'neutral', stale: 'caution', resolved: 'success' }

/** The ticket desk of the operator console: what the case is, what the assistant did, and what the operator can do next. */
export function TicketPanel({ ticket, view, act, reload, loadError, onClose, keyForm, traceLink, loadContext, caseLink, resolveOptions, auditNote }: TicketPanelProps) {
  const t = useT()
  const { locale } = useI18n()
  const customer = useCustomerContext(ticket.ticket_id, loadContext)
  const customerData = customer.result?.ok ? customer.result.data : null
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const [resultCode, setResultCode] = useState<string | null>(null)
  const picking = resolveOptions !== undefined
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
  const evidenceIds = new Set(evidence.flatMap((e) => (e.id ? [e.id] : [])))
  const last = desk.history.at(-1)
  // The filing of the case is an event too, the first of all.
  const events = desk.history.length + 1

  async function run(action: DeskAction) {
    setPending(action)
    setFlash(null)
    try {
      const result = await act(action, {
        expectedVersion: desk.version,
        reason: action === 'reject' ? reason.trim() || undefined : undefined,
        message: action === 'resolve' ? (picking ? message.trim() || undefined : message.trim()) : undefined,
        resultCode: action === 'resolve' && picking ? resultCode ?? undefined : undefined,
      })
      if (result.ok) {
        setConflict(null)
        setReason('')
        setMessage('')
        setResultCode(null)
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
            {[ticket.country, ticket.language ? ticket.language.toUpperCase() : t('operator.queue.unknownLanguage'), ticket.segment && segmentName(t, ticket.segment)].filter(Boolean).map((part) => ` · ${part}`)}
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
        </div>

        <section className="op-sheet op-summary" aria-label={t('operator.ticket.request')}>
          <div className="op-summary__block">
            <h2 className="op-label">{t('operator.ticket.request')}</h2>
            <p className="op-request">“{ticket.request}”</p>
            <p className="op-muted op-summary__reason">{t('operator.ticket.reasonLine', { reason: reasonText(t, ticket), rule: ruleName(t, ticket.policy_rule) })}</p>
            {ticket.prior_requests.length > 0 && (
              <div className="op-summary__prior">
                <h3 className="op-label">{t('operator.ticket.priorRequests')}</h3>
                <ul className="op-plain">{ticket.prior_requests.map((p, i) => <li key={i}>{p}</li>)}</ul>
              </div>
            )}
          </div>
          {!conflict && closed && <Outcome ticket={ticket} resolveOptions={resolveOptions} />}
          <div className="op-sheet__rule" />
          <div className="op-summary__block">
            <h2 className="op-label">{t('operator.ticket.nextStep')}</h2>
            <p className="op-next">{nextStepText(t, ticket)}</p>
          </div>
        </section>

        <Attention ticket={ticket} data={customerData} />

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

        {!closed && !pendingAction && picking && (
          <section className="op-block">
            <fieldset className="op-results" disabled={!mine || locked} aria-describedby="op-results-hint">
              <legend><h2>{t('operator.ticket.outcomePick.label')}</h2></legend>
              <p id="op-results-hint" className="op-muted">{resolveOptions.length ? t('operator.ticket.outcomePick.hint') : t('operator.ticket.outcomePick.none')}</p>
              {resolveOptions.map((option) => (
                <label key={option.code} className="op-result" data-checked={resultCode === option.code ? '' : undefined}>
                  <input type="radio" name="op-result" value={option.code} checked={resultCode === option.code} onChange={() => setResultCode(option.code)} />
                  <span>{option.label}</span>
                </label>
              ))}
            </fieldset>
            <div className="op-block__head">
              <label htmlFor="op-message"><h2>{t('operator.ticket.outcomePick.messageLabel')}</h2></label>
              <span id="op-message-count" className="op-mono op-muted">{`${message.length}/${MESSAGE_MAX}`}</span>
            </div>
            <textarea
              id="op-message"
              className="op-input"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={MESSAGE_MAX}
              rows={2}
              disabled={!mine || locked}
              placeholder={hint('message')}
              aria-describedby="op-message-count op-message-hint"
            />
            <p id="op-message-hint" className="op-muted">{t('operator.ticket.outcomePick.messageHint')}</p>
          </section>
        )}

        {!closed && !pendingAction && !picking && (
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

        <FoldGroup>
          {customer.enabled && <ContextNotice result={customer.result} onRetry={customer.retry} />}
          {customerData?.warehouse.available && (
            <>
              <ProductsFold data={customerData} />
              <MovementsFold data={customerData} inEvidence={evidenceIds} />
            </>
          )}

          {ticket.evidence.length > 0 && (
            <Fold
              id="evidence"
              title={t('operator.ticket.sections.evidence')}
              summary={flagged ? t(flagged === 1 ? 'operator.ticket.sections.flaggedOne' : 'operator.ticket.sections.flaggedOther', { count: ticket.evidence.length, flagged }) : String(ticket.evidence.length)}
            >
              {flagged > 0 && <p className="op-flagged-count">{t(flagged === 1 ? 'operator.ticket.evidence.flaggedOne' : 'operator.ticket.evidence.flaggedOther', { count: flagged, threshold: FRAUD_SCORE_FLAG })}</p>}
              {evidence.length > 0 && (
                <ul className="op-plain op-evrows" aria-label={t('operator.ticket.evidence.caption')}>
                  {evidence.map((e) => {
                    const hot = isFlagged(e)
                    const b = behaviorOf(e)
                    return (
                      <li key={e.id ?? shortStamp(e.detail.transaction_date)} data-flagged={hot ? '' : undefined}>
                        <span className="op-mono op-evrows__date" title={e.id ?? undefined}>{shortStamp(e.detail.transaction_date)}</span>
                        <span className="op-evrows__who">{merchantOf(e) || '—'}</span>
                        <span className="op-mono op-evrows__amount">{money(e.detail.amount, e.detail.currency)}</span>
                        <span className="op-evrows__meta">
                          <span className="op-mono">
                            {hot && (
                              <>
                                <svg className="op-flag" viewBox="0 0 20 20" width="10" height="10" aria-hidden="true" focusable="false"><path d="M5 17V3.5M5 4h9l-2 3.5L14 11H5" fill="currentColor" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" /></svg>
                                <span className="sr-only">{t('operator.ticket.evidence.flag', { score: scoreLabel(e) })}</span>
                              </>
                            )}
                            <span aria-hidden={hot || undefined}>{t('operator.ticket.evidence.score')} {scoreLabel(e)}</span>
                          </span>
                          <span className="op-mono op-evrows__deviation" title={b ? t('operator.ticket.evidence.behaviorHint') : t('operator.ticket.evidence.behaviorNone')} aria-describedby="op-behavior-hint">
                            {t('operator.ticket.evidence.behavior')} {b ? `${Math.round(b.composite)} · ${t(`operator.ticket.evidence.band.${b.band}`)}` : '—'}
                          </span>
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
              {evidence.length > 0 && <p id="op-behavior-hint" className="op-muted">{t('operator.ticket.evidence.behaviorNote')}</p>}
              {otherEvidence.map((e, i) => (
                <div key={i}>
                  <h4>{evidenceTypeName(t, e.type)}{e.id ? ` · ${e.id}` : ''}</h4>
                  <KeyValues data={e.detail} label={(key) => keyName(t, key)} />
                </div>
              ))}
            </Fold>
          )}

          {ticket.verified_facts.length > 0 && (
            <Fold id="facts" title={t('operator.ticket.verifiedFacts')} summary={String(ticket.verified_facts.length)}>
              <ul className="op-facts">
                {ticket.verified_facts.map((fact, i) => (
                  <li key={i}>
                    <CheckIcon size={10} />
                    <span className="op-mono">{Object.entries(fact).map(([k, v]) => `${keyName(t, k)}: ${typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}`).join(' · ')}</span>
                  </li>
                ))}
              </ul>
            </Fold>
          )}

          {customerData && (
            <>
              <CasesFold data={customerData} caseLink={caseLink} />
              <TracesFold data={customerData} />
            </>
          )}

          {ticket.open_questions.length > 0 && (
            <Fold id="questions" title={t('operator.ticket.openQuestions')} summary={String(ticket.open_questions.length)}>
              <ul className="op-bullets">{questionTexts(t, ticket).map((q, i) => <li key={i}>{q}</li>)}</ul>
            </Fold>
          )}

          <Fold
            id="history"
            title={t('operator.ticket.history')}
            summary={[t(events === 1 ? 'operator.ticket.sections.eventsOne' : 'operator.ticket.sections.eventsOther', { count: events }), ticket.trace_id && t('operator.ticket.sections.traceSuffix')].filter(Boolean).join(' · ')}
          >
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
            {ticket.actions_taken.length > 0 && (
              <>
                <h4>{t('operator.ticket.actionsTaken')}</h4>
                <ul className="op-facts">
                  {ticket.actions_taken.map((a, i) => (
                    <li key={i}><span className="op-mono">{String(a.tool ?? a.tool_name ?? '—')}{a.error_type ? ` · ${String(a.error_type)}` : ''}</span></li>
                  ))}
                </ul>
              </>
            )}
          </Fold>
        </FoldGroup>
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
                <Button size="sm" onClick={() => void run('resolve')} loading={pending === 'resolve'} disabled={busy || (picking ? !resultCode : !message.trim())}>{pending === 'resolve' ? t('operator.ticket.actions.sending.resolve') : t('operator.ticket.actions.resolve')}</Button>
              )}
              <span className="op-head__spacer" />
              <Button size="sm" variant="ghost" muted onClick={() => void run('release')} loading={pending === 'release'} disabled={busy}>{pending === 'release' ? t('operator.ticket.actions.sending.release') : t('operator.ticket.actions.release')}</Button>
            </>
          )}
        </div>
        {(mine || closed) && (
          <div className="op-audit">
            <span className="op-muted">{mine && view.operator ? auditNote ?? t('operator.ticket.footer.auditedAs', { name: view.operator }) : ''}</span>
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

/** How a closed case ended, inside the summary card: a mark, the name of the result and, when it has one, the message the customer got. */
function Outcome({ ticket, resolveOptions }: { ticket: Ticket; resolveOptions?: { code: string; label: string }[] }) {
  const t = useT()
  const { desk } = ticket
  const message = resolutionMessage(desk)
  // The predefined result a resolution named, when the screen knows its name (only the demo resolves with one).
  const resultCode = (desk as { result?: unknown }).result
  const result = typeof resultCode === 'string' ? resolveOptions?.find((o) => o.code === resultCode)?.label ?? resultCode : null
  const by = desk.history.at(-1)?.operator ?? desk.operator ?? ''
  const { title, body, tone } =
    desk.status === 'approved' ? { title: t('operator.ticket.banner.traceOpened'), body: desk.trace_id ? t('operator.ticket.banner.traceOpenedBody', { id: desk.trace_id }) : undefined, tone: 'success' as const }
    : desk.status === 'resolved' ? { title: t('operator.ticket.banner.resolvedTitle'), body: message ? t('operator.ticket.outcomeMessage', { name: by, message }) : undefined, tone: 'success' as const }
    : desk.status === 'stale' ? { title: t('operator.ticket.banner.staleTitle'), body: t('operator.ticket.banner.staleBody'), tone: 'caution' as const }
    : desk.status === 'rejected' ? { title: t('operator.ticket.banner.rejectedTitle'), body: t('operator.ticket.banner.rejectedBody'), tone: 'neutral' as const }
    : { title: t('operator.ticket.banner.handedBackTitle'), body: t('operator.ticket.banner.handedBackBody'), tone: 'neutral' as const }
  const Icon = tone === 'caution' ? AlertTriangleIcon : tone === 'success' ? CheckIcon : InfoCircleIcon
  return (
    <div className={`op-outcome op-outcome--${tone}`} role="status">
      <span className="op-outcome__mark"><Icon size={tone === 'success' ? 10 : 14} /></span>
      <div>
        <strong>{title}</strong>
        {result && <p>{t('operator.ticket.outcomePick.resultLine', { result })}</p>}
        {body && <p>{body}</p>}
      </div>
    </div>
  )
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

