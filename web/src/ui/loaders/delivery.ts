// State of the customer's message bubble while it travels to the API. Paper draws three: sending, sent, not sent. The chat adds
// two the design has no frame for: `uncertain` (the answer got lost, so nobody knows whether the API received the message; retrying
// is safe because it travels with the same key) and `processed` (the API did receive it, and only the conversation can show the reply).

export type DeliveryState = 'sending' | 'sent' | 'failed' | 'uncertain' | 'processed'

export type DeliveryView = {
  icon: 'spinner' | 'check' | 'none'
  /** Which dictionary entry names the state (`loaders.delivery.<label>`). */
  label: DeliveryState
  tone: 'muted' | 'danger' | 'caution'
  /** Only a send that did not go through can be retried. */
  retry: boolean
  /** The message was received: the action is to load the conversation again, not to send it again. */
  reload: boolean
  /** The bubble underneath turns danger-tinted. */
  tintedBubble: boolean
  /** The send time is shown next to "Sent" once the state has settled. */
  showTime: boolean
}

const views: Record<DeliveryState, DeliveryView> = {
  sending: { icon: 'spinner', label: 'sending', tone: 'muted', retry: false, reload: false, tintedBubble: false, showTime: false },
  sent: { icon: 'check', label: 'sent', tone: 'muted', retry: false, reload: false, tintedBubble: false, showTime: true },
  failed: { icon: 'none', label: 'failed', tone: 'danger', retry: true, reload: false, tintedBubble: true, showTime: false },
  uncertain: { icon: 'none', label: 'uncertain', tone: 'caution', retry: true, reload: false, tintedBubble: false, showTime: false },
  processed: { icon: 'none', label: 'processed', tone: 'muted', retry: false, reload: true, tintedBubble: false, showTime: false },
}

export function deliveryView(state: DeliveryState): DeliveryView {
  return views[state]
}
