import assert from 'node:assert/strict'
import { test } from 'node:test'
import { KEY_PATTERN } from '../server/chat-core.ts'
import { newMessageKey } from './key.ts'

test('every message gets its own key, and the API accepts its shape', () => {
  const keys = new Set(Array.from({ length: 50 }, newMessageKey))
  assert.equal(keys.size, 50)
  for (const key of keys) assert.match(key, KEY_PATTERN)
})

test('without randomUUID (plain http off localhost) it still makes an acceptable key', () => {
  const original = globalThis.crypto.randomUUID
  // @ts-expect-error simulate an insecure context
  globalThis.crypto.randomUUID = undefined
  try {
    assert.match(newMessageKey(), KEY_PATTERN)
  } finally {
    globalThis.crypto.randomUUID = original
  }
})
