import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clampPage, hasNext, hasPrevious, pageCount, pageItems, pageRange } from './paging.ts'

test('pageCount rounds up and is never below one', () => {
  assert.equal(pageCount(138, 25), 6)
  assert.equal(pageCount(150, 25), 6)
  assert.equal(pageCount(151, 25), 7)
  assert.equal(pageCount(0, 25), 1)
  assert.equal(pageCount(-4, 25), 1)
  assert.equal(pageCount(10, 0), 1)
})

test('clampPage keeps the page inside the range', () => {
  assert.equal(clampPage(0, 138, 25), 1)
  assert.equal(clampPage(-3, 138, 25), 1)
  assert.equal(clampPage(9, 138, 25), 6)
  assert.equal(clampPage(3, 138, 25), 3)
  assert.equal(clampPage(2.9, 138, 25), 2)
  assert.equal(clampPage(Number.NaN, 138, 25), 1)
  assert.equal(clampPage(4, 0, 25), 1)
})

test('pageRange is 1-based and inclusive, and the last page is short', () => {
  assert.deepEqual(pageRange(1, 138, 25), { from: 1, to: 25 })
  assert.deepEqual(pageRange(2, 138, 25), { from: 26, to: 50 })
  assert.deepEqual(pageRange(6, 138, 25), { from: 126, to: 138 })
  assert.deepEqual(pageRange(1, 7, 25), { from: 1, to: 7 })
})

test('pageRange clamps an out-of-range page and reports 0–0 without rows', () => {
  assert.deepEqual(pageRange(99, 138, 25), { from: 126, to: 138 })
  assert.deepEqual(pageRange(1, 0, 25), { from: 0, to: 0 })
})

test('a few pages are all drawn', () => {
  assert.deepEqual(pageItems(1, 1), [1])
  assert.deepEqual(pageItems(3, 6), [1, 2, 3, 4, 5, 6])
  assert.deepEqual(pageItems(4, 7), [1, 2, 3, 4, 5, 6, 7])
})

test('many pages show first, last and a window, with ellipses', () => {
  assert.deepEqual(pageItems(1, 20), [1, 2, 3, 4, 5, 'end-ellipsis', 20])
  assert.deepEqual(pageItems(4, 20), [1, 2, 3, 4, 5, 'end-ellipsis', 20])
  assert.deepEqual(pageItems(10, 20), [1, 'start-ellipsis', 9, 10, 11, 'end-ellipsis', 20])
  assert.deepEqual(pageItems(17, 20), [1, 'start-ellipsis', 16, 17, 18, 19, 20])
  assert.deepEqual(pageItems(20, 20), [1, 'start-ellipsis', 16, 17, 18, 19, 20])
})

test('an ellipsis never hides a single page', () => {
  for (const count of [8, 9, 12, 50]) {
    for (let page = 1; page <= count; page++) {
      const items = pageItems(page, count)
      assert.ok(items.includes(page), `page ${page} of ${count} is drawn`)
      const numbers = items.filter((item): item is number => typeof item === 'number')
      for (let i = 0; i < items.length; i++) {
        if (typeof items[i] !== 'string') continue
        const before = numbers.filter((n) => items.indexOf(n) < i).at(-1) ?? 0
        const after = numbers.find((n) => items.indexOf(n) > i) ?? count + 1
        assert.ok(after - before > 2, `ellipsis at ${i} in page ${page} of ${count} hides at least two pages`)
      }
    }
  }
})

test('previous and next availability', () => {
  assert.equal(hasPrevious(1), false)
  assert.equal(hasPrevious(2), true)
  assert.equal(hasNext(6, 138, 25), false)
  assert.equal(hasNext(5, 138, 25), true)
  assert.equal(hasNext(1, 0, 25), false)
})
