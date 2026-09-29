import { useId, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Button } from '../Button'
import { CheckIcon } from './icons'
import { AssistantFrame, AssistantText } from './MessageFrame'
import './ConfirmTraceMessage.css'

/** The pending movement the assistant proposes to trace. Amount is already formatted in the customer's locale. */
export type TraceItem = { title: string; amount?: string; detail?: string }

/** idle: waiting for the yes. loading: the yes was sent. sent: the request went through. declined: the customer said "not now". */
export type ConfirmTraceState = 'idle' | 'loading' | 'sent' | 'declined'

export type ConfirmTraceMessageProps = {
  /** The proposal ("I found the pending payment. Do you want me to open a trace?"). Already in the customer's language. */
  children: ReactNode
  time?: string
  dateTime?: string
  /** The movement, when the data is at hand. The API sends the proposal as text, so the chat may pass none: the text is then the whole proposal. */
  item?: TraceItem
  state?: ConfirmTraceState
  /** The customer's yes. Tracing never happens without it (ADR-002). */
  onConfirm?: () => void
  onDecline?: () => void
  className?: string
}

/** The one action the assistant can take, proposed and then held until the customer says yes. */
export function ConfirmTraceMessage({ children, time, dateTime, item, state = 'idle', onConfirm, onDecline, className }: ConfirmTraceMessageProps) {
  const t = useT()
  const titleId = useId()
  const answering = state === 'idle' || state === 'loading'
  return (
    <AssistantFrame time={time} dateTime={dateTime} className={className}>
      <AssistantText>{children}</AssistantText>
      <div
        className={item ? 'ui-confirm' : 'ui-confirm ui-confirm--bare'}
        role="group"
        aria-labelledby={item ? titleId : undefined}
        aria-label={item ? undefined : t('chat.confirm.group')}
        aria-busy={state === 'loading' || undefined}
      >
        {item && (
          <>
            <div className="ui-confirm__row">
              <span className="ui-confirm__title" id={titleId}>{item.title}</span>
              {item.amount && <span className="ui-confirm__amount">{item.amount}</span>}
            </div>
            {item.detail && <p className="ui-confirm__detail">{item.detail}</p>}
          </>
        )}
        <div className="ui-confirm__actions">
          {answering && (
            <>
              <Button variant="primary" size="md" loading={state === 'loading'} onClick={onConfirm}>
                {state === 'loading' ? t('chat.confirm.yesLoading') : t('chat.confirm.yes')}
              </Button>
              <Button variant="ghost" size="md" disabled={state === 'loading'} onClick={onDecline}>{t('chat.confirm.no')}</Button>
            </>
          )}
          {/* Always mounted so the outcome is announced when its text appears. */}
          <span className="ui-confirm__outcome" role="status" data-outcome={state === 'sent' || state === 'declined' ? state : undefined}>
            {state === 'sent' && (
              <>
                <CheckIcon size={12} />
                {t('chat.confirm.sent')}
              </>
            )}
            {state === 'declined' && t('chat.confirm.declined')}
          </span>
        </div>
      </div>
    </AssistantFrame>
  )
}
