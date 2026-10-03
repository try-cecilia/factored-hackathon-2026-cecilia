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

test('a scale is exactly a power of ten, or it is refused', () => {
  for (const [scale, power] of [[1, 0], [10, 1], [100, 2], [0.1, -1], [0.01, -2], [0.001, -3], [1e-13, -13], [1e21, 21]] as const) {
    assert.equal(powerOfTen(scale), power, String(scale))
  }
  // Close to a power of ten is not one: rounding the scale first would have read these as 10**-13, -12, -20 and -2.
  for (const scale of [3, 3e-13, 1.3e-12, 2e-20, 0.1 * 0.1, 0.010000000000000002, 0.0099999999999, 20, 1.5]) {
    assert.throws(() => powerOfTen(scale), String(scale))
  }
})
