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

test('failed is the only state with a tinted bubble; it and the uncertain one offer a retry, in danger and caution tone', () => {
  const states: DeliveryState[] = ['sending', 'sent', 'failed', 'uncertain', 'processed']
  assert.deepEqual(states.filter((s) => deliveryView(s).retry), ['failed', 'uncertain'])
  assert.equal(deliveryView('uncertain').tone, 'caution')
  assert.deepEqual(states.filter((s) => deliveryView(s).tintedBubble), ['failed'])
  assert.equal(deliveryView('failed').tone, 'danger')
  assert.equal(deliveryView('failed').icon, 'none')
})

test('a message the API already received is not sent again: its action is to load the conversation', () => {
  const view = deliveryView('processed')
  assert.equal(view.retry, false)
  assert.equal(view.reload, true)
  assert.deepEqual((['sending', 'sent', 'failed', 'uncertain'] as DeliveryState[]).filter((s) => deliveryView(s).reload), [])
})
