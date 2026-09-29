import { useT } from '../../i18n/context'
import { Spinner } from '../Spinner'
import { deliveryView, type DeliveryState } from './delivery.ts'
import './DeliveryStatus.css'

export type DeliveryStatusProps = {
  status: DeliveryState
  /** Send time, already formatted for the customer's locale. Shown next to "Sent". */
  time?: string
  /** Called from the "Retry" button of a failed send. Without it the button is not drawn. */
  onRetry?: () => void
  className?: string
}

/** The line under the customer's bubble: sending, sent, or not sent with a retry. Changes are announced politely. */
export function DeliveryStatus({ status, time, onRetry, className }: DeliveryStatusProps) {
  const t = useT()
  const view = deliveryView(status)
  const text = view.label === 'sent' && view.showTime && time ? t('loaders.delivery.sentAt', { time }) : t(`loaders.delivery.${view.label}`)
  const classes = ['ui-delivery', `ui-delivery--${view.tone}`, className].filter(Boolean).join(' ')
  return (
    <div className={classes} role="status" data-status={status}>
      {view.icon === 'spinner' && <Spinner size={10} tone="ink" />}
      {view.icon === 'check' && (
        <svg className="ui-delivery__check" viewBox="0 0 20 20" width={10} height={10} aria-hidden="true" focusable="false">
          <path d="M5 10.5l3.2 3.2L15 6.8" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      <span className="ui-delivery__text">{text}</span>
      {view.retry && onRetry && (
        <button type="button" className="ui-delivery__retry" onClick={onRetry}>
          {t('loaders.delivery.retry')}
        </button>
      )}
    </div>
  )
}
