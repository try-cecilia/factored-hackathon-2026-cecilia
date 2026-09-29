import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import './UserMessage.css'

export type UserMessageProps = {
  /** What the customer wrote. Line breaks are kept. */
  children: ReactNode
  /** Already formatted in the customer's language. Shown on hover; always present for assistive tech. */
  time?: string
  dateTime?: string
  /** The delivery line under the bubble (`DeliveryStatus`). While it is there the time is not, because the line carries it. */
  footer?: ReactNode
  /** Tints the bubble when the message did not go through: `failed` in danger, `uncertain` in caution. */
  tone?: 'failed' | 'uncertain'
  /** Only for the dev gallery: draws the hover state (time visible) without the pointer. */
  forceState?: 'hover'
  className?: string
}

/** The only bubble: tonal fill, right aligned. */
export function UserMessage({ children, time, dateTime, footer, tone, forceState, className }: UserMessageProps) {
  const t = useT()
  return (
    <article className={className ? `ui-user ${className}` : 'ui-user'} aria-label={t('chat.you')} data-state={forceState}>
      <div className="ui-user__bubble" data-tone={tone}>{children}</div>
      {footer ?? (time && <time className="ui-user__time" dateTime={dateTime}>{time}</time>)}
    </article>
  )
}
