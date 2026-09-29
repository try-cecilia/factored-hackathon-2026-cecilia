import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Button } from '../Button'
import { AssistantFrame, AssistantText } from './MessageFrame'

export type SignInAgainMessageProps = {
  /** Explains that the session ended and that the question is kept. Already in the customer's language. */
  children: ReactNode
  time?: string
  dateTime?: string
  /** Sends the customer to sign in. */
  onSignIn: () => void
  loading?: boolean
  className?: string
}

/** REAUTH_REQUIRED: one button, and the question is kept. */
export function SignInAgainMessage({ children, time, dateTime, onSignIn, loading, className }: SignInAgainMessageProps) {
  const t = useT()
  return (
    <AssistantFrame time={time} dateTime={dateTime} className={className}>
      <AssistantText>{children}</AssistantText>
      <div>
        <Button variant="primary" size="md" loading={loading} onClick={onSignIn}>{t('chat.signIn.action')}</Button>
      </div>
    </AssistantFrame>
  )
}
