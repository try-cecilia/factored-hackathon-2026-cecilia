import { useCallback, useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n/context'
import type { Translate } from '../i18n/translate'
import { Button, CopyIcon } from '../ui'
import { useConversation } from './ConversationProvider'
import { conversationTranscript, hasMessages } from './transcript'

const NOTICE_MS = 2500

export type CopyState = 'ok' | 'error' | null

export type ConversationCopy = {
  /** How the last copy went, for 2.5 s; null the rest of the time. */
  state: CopyState
  /** There is nothing to copy yet. */
  disabled: boolean
  copy: () => Promise<void>
}

/**
 * The conversation as plain text on the clipboard. The state lives where the buttons are drawn from (the bar and the demo panel's
 * drawer, which covers the bar on a phone), so both say how it went and the chat shows it where it covers nothing.
 */
export function useConversationCopy(ended: boolean): ConversationCopy {
  const { locale, t } = useI18n()
  const { entries, cases } = useConversation()
  const [state, setState] = useState<CopyState>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(conversationTranscript(entries, { locale, t, cases, ended }))
      setState('ok')
    } catch {
      setState('error')
    }
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setState(null), NOTICE_MS)
  }, [entries, cases, locale, t, ended])

  return { state, disabled: !hasMessages(entries), copy }
}

export const copyNoticeText = (t: Translate, state: CopyState): string =>
  state === 'ok' ? t('conversation.copy.copied') : state === 'error' ? t('conversation.copy.failed') : ''

/** The "copy conversation" button, and the result said to the screen reader. The eye reads it in `CopyNotice`, away from the content. */
export function CopyConversation({ copy }: { copy: ConversationCopy }) {
  const { t } = useI18n()
  return (
    <span className="shell__copy">
      <Button variant="ghost" size="sm" title={t('conversation.copy.action')} disabled={copy.disabled} leadingIcon={<CopyIcon size={14} />} onClick={() => void copy.copy()}>
        <span className="shell__copy-label">{t('conversation.copy.action')}</span>
      </Button>
      <span className="sr-only" role="status">{copyNoticeText(t, copy.state)}</span>
    </span>
  )
}

/** What the eye reads of the result; the screen reader has it from the button. Nothing while there is no result. */
export function CopyNotice({ state, className }: { state: CopyState; className?: string }) {
  const { t } = useI18n()
  if (!state) return null
  return <span className={className} data-outcome={state} aria-hidden="true">{copyNoticeText(t, state)}</span>
}
