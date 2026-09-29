import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import './MessageFrame.css'

export type AssistantFrameProps = {
  children: ReactNode
  /** Already formatted in the customer's language ("8:52 AM"). */
  time?: string
  /** Machine-readable time for the <time> element. */
  dateTime?: string
  /** 8px between the parts of the body instead of 10 (answer and limited-mode reply). */
  tight?: boolean
  className?: string
}

/** Shared shell of every assistant message: avatar, "Cecilia" and the time on top, the variant's content below. */
export function AssistantFrame({ children, time, dateTime, tight, className }: AssistantFrameProps) {
  const t = useT()
  return (
    <article className={className ? `ui-msg ${className}` : 'ui-msg'} aria-label={t('chat.assistant')}>
      <div className="ui-msg__avatar" aria-hidden="true">
        <img src="/cecilia-avatar.png" alt="" width={36} height={36} />
      </div>
      <div className={tight ? 'ui-msg__body ui-msg__body--tight' : 'ui-msg__body'}>
        <div className="ui-msg__head">
          <span className="ui-msg__name">{t('chat.assistant')}</span>
          {time && <time className="ui-msg__time" dateTime={dateTime}>{time}</time>}
        </div>
        {children}
      </div>
    </article>
  )
}

/** The assistant's words, open on the page. Already in the customer's language: it is never translated here. */
export function AssistantText({ children }: { children: ReactNode }) {
  return <div className="ui-msg__text">{children}</div>
}
