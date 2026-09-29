import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Button } from '../Button'
import { AlertCircleIcon } from './icons'
import { AssistantFrame } from './MessageFrame'
import './CouldNotVerifyMessage.css'

export type CouldNotVerifyMessageProps = {
  /** "I couldn't verify…": what failed, that nothing changed, who follows up. Already in the customer's language. */
  children: ReactNode
  time?: string
  dateTime?: string
  /** Shows "Try again". Without it the message has no action. */
  onRetry?: () => void
  retrying?: boolean
  className?: string
}

/** A lookup failed: the assistant does not guess, says nothing changed, and offers a retry. */
export function CouldNotVerifyMessage({ children, time, dateTime, onRetry, retrying, className }: CouldNotVerifyMessageProps) {
  const t = useT()
  return (
    <AssistantFrame time={time} dateTime={dateTime} className={className}>
      <div className="ui-msg-tint ui-msg-tint--danger">
        <AlertCircleIcon className="ui-unverified__icon" />
        <p className="ui-unverified__text">{children}</p>
      </div>
      {onRetry && (
        <div className="ui-unverified__actions">
          <Button variant="ghost" tinted size="sm" loading={retrying} onClick={onRetry}>
            {retrying ? t('chat.couldNotVerify.retrying') : t('chat.couldNotVerify.retry')}
          </Button>
        </div>
      )}
    </AssistantFrame>
  )
}
