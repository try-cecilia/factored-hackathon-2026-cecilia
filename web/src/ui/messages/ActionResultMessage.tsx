import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { CheckIcon, CrossIcon } from './icons'
import { AssistantFrame } from './MessageFrame'
import './ActionResultMessage.css'

export type ActionResultMessageProps = {
  /** ok: the trace was read back from the service. failed: it was not opened, nothing changed. */
  status: 'ok' | 'failed'
  /** Overrides the default headline ("Trace opened" / "The trace could not be opened"). */
  title?: string
  /** Service reference, drawn in DM Mono ("trace_6f3a91c2"). */
  reference?: string
  /** The detail after the reference ("status open · you'll hear back within 2 business days"). Already in the customer's language. */
  children?: ReactNode
  time?: string
  dateTime?: string
  className?: string
}

/** Result of the trace, announced only once the service confirms it. */
export function ActionResultMessage({ status, title, reference, children, time, dateTime, className }: ActionResultMessageProps) {
  const t = useT()
  const ok = status === 'ok'
  return (
    <AssistantFrame time={time} dateTime={dateTime} className={className}>
      <div className={`ui-msg-tint ${ok ? 'ui-msg-tint--success' : 'ui-msg-tint--danger'} ui-result`}>
        <span className={`ui-result__badge ${ok ? 'ui-result__badge--ok' : 'ui-result__badge--failed'}`} aria-hidden="true">
          {ok ? <CheckIcon /> : <CrossIcon />}
        </span>
        <div className="ui-result__body">
          <span className="ui-result__title">{title ?? t(ok ? 'chat.actionResult.okTitle' : 'chat.actionResult.failedTitle')}</span>
          {(reference || children) && (
            <p className="ui-result__detail">
              {reference && <span className="ui-result__ref">{reference}</span>}
              {reference && children ? ' · ' : null}
              {children}
            </p>
          )}
        </div>
      </div>
    </AssistantFrame>
  )
}
