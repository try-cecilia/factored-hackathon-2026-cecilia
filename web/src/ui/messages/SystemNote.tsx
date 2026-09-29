import type { ReactNode } from 'react'
import './SystemNote.css'

/** The dot says what kind of event it is: info (blue), success (green), neutral (gray). */
export type SystemNoteTone = 'info' | 'success' | 'neutral'

export type SystemNoteProps = {
  children: ReactNode
  tone?: SystemNoteTone
  /** Already formatted; drawn after the text ("… · 10:42"). */
  time?: string
  dateTime?: string
  className?: string
}

/** An event in the conversation, not a message: centered, muted, on a subtle pill. */
export function SystemNote({ children, tone = 'neutral', time, dateTime, className }: SystemNoteProps) {
  return (
    <p className={className ? `ui-note ${className}` : 'ui-note'}>
      <span className={`ui-note__dot ui-note__dot--${tone}`} aria-hidden="true" />
      <span>
        {children}
        {time && (
          <>
            {' · '}
            <time dateTime={dateTime}>{time}</time>
          </>
        )}
      </span>
    </p>
  )
}

/** "Today": a centered label between two tonal rules that separates the days of the conversation. */
export function SystemDivider({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={className ? `ui-note-divider ${className}` : 'ui-note-divider'}>
      <span className="ui-note-divider__rule" aria-hidden="true" />
      <span className="ui-note-divider__label">{children}</span>
      <span className="ui-note-divider__rule" aria-hidden="true" />
    </div>
  )
}
