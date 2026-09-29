import { useCallback, useEffect, useState } from 'react'
import type { CaseRead, CaseRow } from '../chat/ConversationProvider'
import { caseCategoryKey, caseTone, shortCaseId } from '../chat/conversation'
import { useI18n, useT } from '../i18n/context'
import { htmlLang } from '../i18n/locales'
import { Button, IconButton, Skeleton } from '../ui'
import { statusLabel } from './CasesSection'
import './CaseView.css'

const STATUSES = ['open', 'claimed', 'approved', 'rejected', 'handed_back', 'stale'] as const
type Known = (typeof STATUSES)[number] | 'unknown'
const known = (status: string): Known => ((STATUSES as readonly string[]).includes(status) ? (status as Known) : 'unknown')

/**
 * One case, as the customer can follow it: what it is about, where it stands, what is happening and what comes next, and the
 * last news the API worded for them. Everything comes from `GET /case/{id}` (status and news) and from the conversation's
 * index of cases (reason and date); the API keeps no history of a case's news, so none is drawn.
 */
export function CaseView({ ticketId, row, ended, titleId, refresh, onClose, onShowInChat }: {
  ticketId: string
  /** What the conversation knows of the case; undefined while it was never asked. */
  row: CaseRow | undefined
  ended: boolean
  titleId: string
  refresh: (ticketId: string) => Promise<CaseRead>
  onClose: () => void
  /** Brings the handoff message into view; left out when the message is not on the page (older than the turns kept). */
  onShowInChat?: (ticketId: string) => void
}) {
  const t = useT()
  const { locale } = useI18n()
  const [refreshing, setRefreshing] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; at: number } | null>(null)

  // A failed read is always said (the status on screen is the last one known, not the present one); a good one only when the
  // customer asked for it (`announce`), with the time it was read.
  const update = useCallback(async (announce: boolean) => {
    setRefreshing(true)
    const read = await refresh(ticketId)
    setRefreshing(false)
    // A read that a newer one overtook says nothing: the newer one does.
    if (read === 'superseded') return
    if (read === 'error') setNote({ ok: false, at: Date.now() })
    else if (announce) setNote(read === 'ready' ? { ok: true, at: Date.now() } : null)
  }, [refresh, ticketId])

  // Opening the case asks for it again: the sidebar may be showing an answer from a while ago.
  useEffect(() => {
    setNote(null)
    void update(false)
  }, [update])

  const state = row?.state ?? { state: 'loading' as const }
  const title = row ? t(`cases.category.${caseCategoryKey(row.ref.category)}` as 'cases.category.other') : t('cases.title')
  const time = new Intl.DateTimeFormat(htmlLang[locale], { hour: '2-digit', minute: '2-digit' })
  const date = new Intl.DateTimeFormat(htmlLang[locale], { dateStyle: 'long', timeStyle: 'short' })

  return (
    <div className="case">
      <header className="case__head">
        <div className="case__heading">
          <p className="case__eyebrow">
            {t('cases.detail.eyebrow')} <span className="case__mono">#{shortCaseId(ticketId)}</span>
          </p>
          <h2 id={titleId} className="case__title">{title}</h2>
        </div>
        <IconButton
          variant="ghost"
          size="sm"
          label={t('cases.detail.close')}
          icon={<svg viewBox="0 0 20 20" width={14} height={14} aria-hidden="true" focusable="false"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" /></svg>}
          onClick={onClose}
        />
      </header>

      {ended ? (
        <p className="case__notice" role="status">{t('cases.detail.ended')}</p>
      ) : state.state === 'loading' ? (
        <div className="case__loading" role="status">
          <span className="sr-only">{t('cases.loading')}</span>
          <Skeleton width={120} height={10} radius="var(--radius-pill)" />
          <Skeleton width="85%" height={10} radius="var(--radius-pill)" />
          <Skeleton width="70%" height={10} radius="var(--radius-pill)" />
        </div>
      ) : state.state === 'error' ? (
        <div className="case__problem" role="alert">
          <h3>{t('cases.detail.error.title')}</h3>
          <p>{t('cases.detail.error.body')}</p>
          <Button variant="ghost" size="sm" tinted loading={refreshing} onClick={() => void update(true)}>{t('cases.detail.error.retry')}</Button>
        </div>
      ) : state.state === 'not_found' ? (
        <div className="case__problem" role="alert">
          <h3>{t('cases.detail.notFound.title')}</h3>
          <p>{t('cases.detail.notFound.body')}</p>
        </div>
      ) : (
        <>
          <div className="case__status">
            <span className="case__dot" data-tone={caseTone(state.status)} aria-hidden="true" />
            <strong>{row ? statusLabel(t, row) : null}</strong>
            {row && <span className="case__opened">{t('cases.detail.opened', { date: date.format(row.ref.at) })}</span>}
          </div>
          <section className="case__section" aria-labelledby={`${titleId}-now`}>
            <h3 id={`${titleId}-now`}>{t('cases.detail.now')}</h3>
            <p>{t(`cases.detail.whatNow.${known(state.status)}`)}</p>
            {state.message && (
              <div className="case__news">
                <span className="case__label">{t('cases.detail.latest')}</span>
                <p>{state.message}</p>
              </div>
            )}
          </section>
          <section className="case__section" aria-labelledby={`${titleId}-next`}>
            <h3 id={`${titleId}-next`}>{t('cases.detail.next')}</h3>
            <p>{t(`cases.detail.whatNext.${known(state.status)}`)}</p>
          </section>
          <dl className="case__facts">
            <dt>{t('cases.detail.number')}</dt>
            <dd className="case__mono">{ticketId}</dd>
          </dl>
        </>
      )}

      <div className="case__foot">
        {!ended && state.state === 'ready' && (
          <Button variant="ghost" size="sm" tinted loading={refreshing} onClick={() => void update(true)}>{t('cases.detail.refresh')}</Button>
        )}
        {onShowInChat && <Button variant="ghost" size="sm" onClick={() => onShowInChat(ticketId)}>{t('cases.detail.showInChat')}</Button>}
        <p className="case__note" role="status">
          {note && state.state === 'ready' ? (note.ok ? t('cases.detail.refreshed', { time: time.format(note.at) }) : t('cases.detail.refreshFailed')) : ''}
        </p>
      </div>
    </div>
  )
}
