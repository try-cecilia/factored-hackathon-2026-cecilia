import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n/context'
import { Button, CopyIcon } from '../ui'
import { useConversation } from './ConversationProvider'
import { conversationTranscript, hasMessages } from './transcript'

const NOTICE_MS = 2500

/** The bar's "copy conversation": the whole conversation as plain text on the clipboard, and the result said to the eye and to the screen reader. */
export function CopyConversation() {
  const { locale, t } = useI18n()
  const { entries, cases } = useConversation()
  const [copied, setCopied] = useState<'ok' | 'error' | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(conversationTranscript(entries, { locale, t, cases }))
      setCopied('ok')
    } catch {
      setCopied('error')
    }
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(null), NOTICE_MS)
  }

  const said = copied === 'ok' ? t('conversation.copy.copied') : copied === 'error' ? t('conversation.copy.failed') : ''
  return (
    <span className="shell__copy">
      <Button variant="ghost" size="sm" disabled={!hasMessages(entries)} leadingIcon={<CopyIcon size={14} />} onClick={() => void copy()}>
        <span className="shell__copy-label">{t('conversation.copy.action')}</span>
      </Button>
      <span className="sr-only" role="status">{said}</span>
      {copied && <span className="shell__copied" data-outcome={copied} aria-hidden="true">{said}</span>}
    </span>
  )
}
