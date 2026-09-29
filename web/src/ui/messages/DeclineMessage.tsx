import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { AssistantFrame, AssistantText } from './MessageFrame'
import { QuickReplies, type QuickReply } from './QuickReplies'

export type DeclineMessageProps = {
  /** Says what the assistant cannot do and what it can. Already in the customer's language. */
  children: ReactNode
  time?: string
  dateTime?: string
  /** What the assistant can do instead, one tap each. */
  suggestions?: QuickReply[]
  onSelect?: (value: string) => void
  disabled?: boolean
  className?: string
}

/** Outside scope or not allowed: the assistant says so and offers what it can do. */
export function DeclineMessage({ children, time, dateTime, suggestions, onSelect, disabled, className }: DeclineMessageProps) {
  const t = useT()
  return (
    <AssistantFrame time={time} dateTime={dateTime} className={className}>
      <AssistantText>{children}</AssistantText>
      {suggestions && suggestions.length > 0 && (
        <QuickReplies options={suggestions} onSelect={onSelect} disabled={disabled} label={t('chat.decline.suggestions')} />
      )}
    </AssistantFrame>
  )
}
