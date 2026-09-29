// State of the customer's message bubble while it travels to the API. Paper draws three: sending, sent, not sent.

export type DeliveryState = 'sending' | 'sent' | 'failed'

export type DeliveryView = {
  icon: 'spinner' | 'check' | 'none'
  /** Which dictionary entry names the state (`loaders.delivery.<label>`). */
  label: 'sending' | 'sent' | 'failed'
  tone: 'muted' | 'danger'
  /** Only a failed send can be retried. */
  retry: boolean
  /** The bubble underneath turns danger-tinted. */
  tintedBubble: boolean
  /** The send time is shown next to "Sent" once the state has settled. */
  showTime: boolean
}

const views: Record<DeliveryState, DeliveryView> = {
  sending: { icon: 'spinner', label: 'sending', tone: 'muted', retry: false, tintedBubble: false, showTime: false },
  sent: { icon: 'check', label: 'sent', tone: 'muted', retry: false, tintedBubble: false, showTime: true },
  failed: { icon: 'none', label: 'failed', tone: 'danger', retry: true, tintedBubble: true, showTime: false },
}

export function deliveryView(state: DeliveryState): DeliveryView {
  return views[state]
}
