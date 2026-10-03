import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { powerOfTen, roundHalfUp } from './rounding.ts'

type Case = { value: number; digits: number; shift?: number; expected: string }
// The same file eval/check_readme.py tests its `_fixed` with: both sides must give the same text for every case.
const { cases } = JSON.parse(readFileSync(new URL('./rounding-cases.json', import.meta.url), 'utf8')) as { cases: Case[] }

test('the landing rounds every shared case exactly as eval/check_readme.py does', () => {
  for (const { value, digits, shift, expected } of cases) assert.equal(roundHalfUp(value, digits, shift), expected, `${value} (${digits}, ${shift ?? 0})`)
})

test('rounding works on the decimal text, not on the binary float that toFixed rounds', () => {
  assert.equal((2.55).toFixed(1), '2.5') // the binary value is 2.54999…: this is what the contract avoids
  assert.equal(roundHalfUp(2.55, 1), '2.6')
  assert.equal(Number((2.449999999999).toPrecision(12)).toFixed(1), '2.5') // and what toPrecision(12) used to add
  assert.equal(roundHalfUp(2.449999999999, 1), '2.4')
})

test('a scale is a power of ten, or it is refused', () => {
  assert.equal(powerOfTen(100), 2)
  assert.equal(powerOfTen(0.001), -3)
  assert.equal(powerOfTen(1), 0)
  assert.throws(() => powerOfTen(3))
})
