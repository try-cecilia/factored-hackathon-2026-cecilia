import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import './UserMessage.css'

export type UserMessageProps = {
  /** What the customer wrote. Line breaks are kept. */
  children: ReactNode
  /** Already formatted in the customer's language. Shown on hover; always present for assistive tech. */
  time?: string
  dateTime?: string
  /** Only for the dev gallery: draws the hover state (time visible) without the pointer. */
  forceState?: 'hover'
  className?: string
}

/** The only bubble: tonal fill, right aligned. */
export function UserMessage({ children, time, dateTime, forceState, className }: UserMessageProps) {
  const t = useT()
  return (
    <article className={className ? `ui-user ${className}` : 'ui-user'} aria-label={t('chat.you')} data-state={forceState}>
      <div className="ui-user__bubble">{children}</div>
      {time && <time className="ui-user__time" dateTime={dateTime}>{time}</time>}
    </article>
  )
}
