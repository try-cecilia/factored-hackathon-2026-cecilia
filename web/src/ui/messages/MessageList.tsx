import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import './MessageList.css'

/** The conversation. A polite log: a new message is announced when it is added, without interrupting what is being read. */
export function MessageList({ children, className }: { children: ReactNode; className?: string }) {
  const t = useT()
  return (
    <div className={className ? `ui-msglist ${className}` : 'ui-msglist'} role="log" aria-live="polite" aria-relevant="additions" aria-label={t('chat.list.label')}>
      {children}
    </div>
  )
}
