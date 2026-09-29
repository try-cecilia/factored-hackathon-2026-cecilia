import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { AssistantFrame, AssistantText } from './MessageFrame'
import { QuickReplies, type QuickReply } from './QuickReplies'

export type ClarifyMessageProps = {
  /** The question. Already in the customer's language. */
  children: ReactNode
  time?: string
  dateTime?: string
  /** The options the customer can pick; labels come from the data. */
  options: QuickReply[]
  onSelect?: (value: string) => void
  /** The option already chosen: it stays highlighted and the rest stop answering. */
  selectedValue?: string
  disabled?: boolean
  className?: string
}

/** One missing detail: the question and its answers as chips. */
export function ClarifyMessage({ children, time, dateTime, options, onSelect, selectedValue, disabled, className }: ClarifyMessageProps) {
  const t = useT()
  return (
    <AssistantFrame time={time} dateTime={dateTime} className={className}>
      <AssistantText>{children}</AssistantText>
      <QuickReplies options={options} onSelect={onSelect} selectedValue={selectedValue} disabled={disabled} label={t('chat.clarify.options')} />
    </AssistantFrame>
  )
}
