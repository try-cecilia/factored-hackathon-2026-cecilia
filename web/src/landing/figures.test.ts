import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'node:test'
import { classifierDate, figures, formatDate, formatFigure, formatMillions, formatNumber, formatShortDate, liveRunDate, redTeamDate } from './figures.ts'

const root = resolve(import.meta.dirname, '../../..')
const files = new Map<string, string>()
const read = (path: string) => files.get(path) ?? files.set(path, readFileSync(resolve(root, path), 'utf8')).get(path)!

const words: Record<string, string> = { none: '0', one: '1', two: '2', three: '3', four: '4', five: '5' }

/** The numbers a quote holds: thousands separators dropped, number words read as digits. */
function numbers(quote: string): number[] {
  const plain = quote.replace(/\b(none|one|two|three|four|five)\b/gi, (w) => words[w.toLowerCase()]).replace(/(\d),(?=\d{3}\b)/g, '$1')
  return [...plain.matchAll(/\d+(?:\.\d+)?/g)].map((m) => Number(m[0]))
}

test('every landing figure is still in the file it cites', () => {
  for (const [name, figure] of Object.entries(figures)) {
    assert.ok(read(figure.source).includes(figure.quote), `${name}: "${figure.quote}" is no longer in ${figure.source}`)
  }
})

/** Figures the source gives as a span, not as a number: the landing shows the length. */
const derived: Record<string, (quote: string) => number> = {
  redTeamMinutes: (quote) => {
    const [start, end] = [...quote.matchAll(/(\d{2}):(\d{2})/g)].map(([, h, m]) => Number(h) * 60 + Number(m))
    return end - start
  },
}

test('every landing figure says what its quote says, at the decimals the landing shows', () => {
  for (const [name, figure] of Object.entries(figures)) {
    if (name in derived) {
      assert.equal(derived[name](figure.quote), figure.value, name)
      continue
    }
    const shown = figure.value.toFixed(figure.digits)
    const found = numbers(figure.quote).some((n) => n.toFixed(figure.digits) === shown)
    assert.ok(found, `${name}: the landing shows ${shown}, "${figure.quote}" (${figure.source}) does not`)
  }
})

test('every date the landing shows is written in the file it cites', () => {
  for (const day of [liveRunDate, redTeamDate, classifierDate]) {
    assert.ok(read(day.source).includes(day.quote), `${day.quote} (${day.source})`)
    const [y, m, d] = day.iso.split('-')
    assert.ok(day.quote.includes(day.iso) || day.quote.includes(`${d}/${m}/${y}`), `${day.iso} is not in "${day.quote}"`)
  }
})

test('figures come out in the notation of each language', () => {
  assert.equal(formatNumber(4316, 0, 'es'), '4.316')
  assert.equal(formatNumber(150000, 0, 'pt'), '150.000')
  assert.equal(formatNumber(0.0034, 4, 'es'), '0,0034')
  assert.equal(formatNumber(95, 1, 'pt'), '95,0')
  assert.equal(formatFigure(figures.classifier, 'es'), '84,7')
  assert.equal(formatMillions(figures.transactions, 'es'), '4,4')
  assert.equal(formatDate(liveRunDate.iso, 'es'), '2 de octubre de 2026')
  assert.equal(formatDate(liveRunDate.iso, 'pt'), '2 de outubro de 2026')
  assert.equal(formatShortDate(liveRunDate.iso, 'es'), '02/10/2026')
  assert.equal(formatShortDate(redTeamDate.iso, 'pt'), '30/09/2026')
})
