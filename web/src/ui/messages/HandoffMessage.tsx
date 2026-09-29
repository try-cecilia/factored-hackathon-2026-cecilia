import { useId, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { AssistantFrame, AssistantText } from './MessageFrame'
import './HandoffMessage.css'

export type HandoffMessageProps = {
  /** Confirms the case was passed on. Already in the customer's language. */
  children: ReactNode
  time?: string
  dateTime?: string
  /** What the case is about ("Unrecognized charge"). */
  title: string
  /** Where the case stands ("With the fraud team"). */
  status: string
  /** The case number without the "#". Drawn in DM Mono. */
  caseId: string
  /** Opens the case. Without it the "View case" link is not drawn. */
  onViewCase?: () => void
  className?: string
}

/** Escalated: the assistant reads the case back with its reference and where it stands. */
export function HandoffMessage({ children, time, dateTime, title, status, caseId, onViewCase, className }: HandoffMessageProps) {
  const t = useT()
  const titleId = useId()
  return (
    <AssistantFrame time={time} dateTime={dateTime} className={className}>
      <AssistantText>{children}</AssistantText>
      <div className="ui-handoff" role="group" aria-labelledby={titleId}>
        <span className="ui-handoff__dot" aria-hidden="true" />
        <div className="ui-handoff__info">
          <span className="ui-handoff__title" id={titleId}>{title}</span>
          <span className="ui-handoff__status">
            {status} · <span className="ui-handoff__id">#{caseId}</span>
          </span>
        </div>
        {onViewCase && (
          <button type="button" className="ui-handoff__link" aria-label={t('chat.handoff.viewCaseFor', { id: caseId })} onClick={onViewCase}>
            {t('chat.handoff.viewCase')}
          </button>
        )}
      </div>
    </AssistantFrame>
  )
}
