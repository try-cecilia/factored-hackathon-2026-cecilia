import assert from 'node:assert/strict'
import { test } from 'node:test'
import { placeMenu } from './placement.ts'

const menu = { width: 200, height: 146 }
const viewport = { width: 1000, height: 800 }

test('opens below the trigger with the right edges aligned', () => {
  const at = placeMenu({ left: 300, top: 100, width: 28, height: 28 }, menu, viewport)
  assert.deepEqual(at, { left: 128, top: 134, placement: 'below' })
})

test('flips above when there is no room below but there is above', () => {
  const at = placeMenu({ left: 300, top: 700, width: 28, height: 28 }, menu, viewport)
  assert.equal(at.placement, 'above')
  assert.equal(at.top, 700 - 6 - 146)
})

test('stays below when it fits in neither direction, pinned inside the viewport', () => {
  const at = placeMenu({ left: 300, top: 60, width: 28, height: 28 }, menu, { width: 1000, height: 200 })
  assert.equal(at.placement, 'below')
  assert.equal(at.top, 200 - 8 - 146)
})

test('never leaves the viewport horizontally', () => {
  assert.equal(placeMenu({ left: 20, top: 100, width: 28, height: 28 }, menu, viewport).left, 8)
  assert.equal(placeMenu({ left: 990, top: 100, width: 28, height: 28 }, menu, viewport).left, 1000 - 8 - 200)
})
