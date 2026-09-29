import assert from 'node:assert/strict'
import { test } from 'node:test'
import { deliveryView, type DeliveryState } from './delivery.ts'

test('sending shows a spinner and nothing to retry', () => {
  const view = deliveryView('sending')
  assert.equal(view.icon, 'spinner')
  assert.equal(view.label, 'sending')
  assert.equal(view.retry, false)
  assert.equal(view.showTime, false)
})

test('sent shows a check and the time', () => {
  const view = deliveryView('sent')
  assert.equal(view.icon, 'check')
  assert.equal(view.tone, 'muted')
  assert.equal(view.showTime, true)
})

test('failed is the only state that offers a retry, in danger tone with a tinted bubble', () => {
  const states: DeliveryState[] = ['sending', 'sent', 'failed']
  assert.deepEqual(states.filter((s) => deliveryView(s).retry), ['failed'])
  assert.deepEqual(states.filter((s) => deliveryView(s).tintedBubble), ['failed'])
  assert.equal(deliveryView('failed').tone, 'danger')
  assert.equal(deliveryView('failed').icon, 'none')
})
