import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'node:test'
import { es } from '../i18n/es.ts'
import { pt } from '../i18n/pt.ts'
import { powerOfTen, roundHalfUp } from './rounding.ts'
import { classifierDate, figures, formatDate, formatFigure, formatMillions, formatNumber, formatShortDate, liveRunDate, offlineRunDate, redTeamDate, type Day, type Figure } from './figures.ts'

const root = resolve(import.meta.dirname, '../../..')
const files = new Map<string, string>()
const read = (path: string) => files.get(path) ?? files.set(path, readFileSync(resolve(root, path), 'utf8')).get(path)!
const parsed = new Map<string, unknown>()
const readJson = (path: string) => parsed.get(path) ?? parsed.set(path, JSON.parse(read(path))).get(path)
/** The public export removes the per-case reports (eval/reports/system_eval*.json carry dataset ids): in that copy, what is bound
 * to them is checked in the team's repository, where they exist. Any other missing source still fails. */
const removedByExport = (source: string) => /^eval\/reports\/system_eval[^/]*\.json$/.test(source) && !existsSync(resolve(root, source))

function field(path: string, at: ReadonlyArray<string | number>): unknown {
  let node = readJson(path)
  for (const key of at) node = (node as Record<string | number, unknown> | null)?.[key]
  return node
}

const words: Record<string, string> = { none: '0', one: '1', two: '2', three: '3', four: '4', five: '5' }

/** The numbers a quote holds, in order and as written: thousands separators dropped, number words read as digits. */
function numbers(quote: string): string[] {
  const plain = quote.replace(/\b(none|one|two|three|four|five)\b/gi, (w) => words[w.toLowerCase()]).replace(/(\d),(?=\d{3}\b)/g, '$1')
  return [...plain.matchAll(/\d+(?:\.\d+)?/g)].map((m) => m[0])
}

/** Figures the source gives as a span, not as a number: the landing shows the length. */
const derived: Record<string, (figure: Figure) => number> = {
  redTeamMinutes: (figure) => {
    const [start, end] = [...('quote' in figure ? figure.quote : '').matchAll(/(\d{2}):(\d{2})/g)].map(([, h, m]) => Number(h) * 60 + Number(m))
    return end - start
  },
}

/** Why `figure` does not match the one value it is bound to, or null when it does. */
function mismatch(name: string, figure: Figure): string | null {
  // Both sides go through the shared rounding (rounding.ts, eval/check_readme.py's _fixed): decimal text, half up.
  const shown = roundHalfUp(figure.value, figure.digits)
  // A quote must be in its file, derived or not: otherwise any made-up quote would back any figure.
  if ('quote' in figure && !read(figure.source).includes(figure.quote)) return `${name}: "${figure.quote}" is no longer in ${figure.source}`
  if (name in derived) return derived[name](figure) === figure.value ? null : `${name}: derived ${derived[name](figure)}, shown ${shown}`
  let source: number | string
  let shift = 0
  if ('rows' in figure) {
    const list = field(figure.source, figure.rows)
    if (!Array.isArray(list)) return `${name}: ${figure.source} has no rows at ${figure.rows.join(' › ')}`
    const matches = (row: Record<string, unknown>) =>
      Object.entries(figure.where).every(([key, want]) => (typeof want === 'boolean' ? (Array.isArray(row[key]) ? (row[key] as unknown[]).length > 0 : Boolean(row[key])) === want : row[key] === want))
    source = list.filter(matches).length
  } else if ('at' in figure) {
    const value = field(figure.source, figure.at)
    if (figure.count) source = value && typeof value === 'object' ? Object.keys(value).length : NaN
    else if (typeof value !== 'number') return `${name}: ${figure.source} has no number at ${figure.at.join(' › ')}`
    else {
      source = value
      shift = powerOfTen(figure.scale ?? 1)
    }
  } else {
    const found = numbers(figure.quote)
    if (found.length > 1 && figure.pick === undefined) return `${name}: "${figure.quote}" holds ${found.length} numbers, say which one`
    const picked = found[figure.pick ?? 0]
    if (picked === undefined) return `${name}: "${figure.quote}" has no number ${figure.pick ?? 0}`
    source = picked
    shift = powerOfTen(figure.scale ?? 1)
  }
  const rounded = roundHalfUp(source, figure.digits, shift)
  return rounded === shown ? null : `${name}: the landing shows ${shown}, ${figure.source} says ${rounded}`
}

test('every landing figure is the value it is bound to, at the decimals the landing shows', () => {
  for (const [name, figure] of Object.entries(figures)) if (!removedByExport(figure.source)) assert.equal(mismatch(name, figure), null)
})

test('a figure taken from the wrong column, percentile, unit or row is rejected', () => {
  const wrong: Array<[keyof typeof figures, number]> = [
    ['keywordSafe', 99.2], // the ideal model's column
    ['sonnetP50', 4.2], // the p95
    ['haikuP50', 1.9], // Sonnet's latency
    ['loadChatsPerSecond', 5.7], // the refusal time, in ms
    ['sonnetSafe', 45.6], // automation attempted, over the 138 instead of the 60 in scope
    ['ablationNoneBad', 17.5], // the ideal model's column
    ['redTeamSessions', 224], // the turns
    ['guardRecall', 0], // the false escalations
    ['attemptsPerProvider', 4], // two providers × two attempts is not the per-provider constant
    ['haikuUnsafeRun2', 0], // run 2 had Haiku's one unsafe outcome
    ['sonnetMissedRun3', 1], // Sonnet missed its escalation in runs 1 and 2, not 3
    ['sonnetRecall', 100], // run 3's recall, not run 1's
  ]
  for (const [name, value] of wrong) {
    if (!removedByExport(figures[name].source)) assert.notEqual(mismatch(name, { ...figures[name], value }), null, `${name} = ${value} passed`)
  }
  // A derived figure needs its quote too: a made-up span that says 120 minutes is not in RED_TEAM.md.
  assert.notEqual(mismatch('redTeamMinutes', { ...figures.redTeamMinutes, value: 120, quote: '30/09/2026, from 20:00 to 22:00' }), null)
  assert.notEqual(mismatch('redTeamMinutes', { ...figures.redTeamMinutes, value: 120 }), null)
  assert.notEqual(mismatch('ambiguous', { value: 70.2, digits: 1, source: 'README.md', quote: '| Safe automated resolution | 70.2% [64.1–75.6] |' }), null)
})

test('every date the landing shows is written in the file it cites', () => {
  for (const day of [liveRunDate, offlineRunDate, redTeamDate, classifierDate] satisfies Day[]) {
    if (removedByExport(day.source)) continue
    if ('at' in day) {
      assert.match(String(field(day.source, day.at)), new RegExp(`^${day.iso}`), day.source)
      continue
    }
    assert.ok(read(day.source).includes(day.quote), `${day.quote} (${day.source})`)
    const [y, m, d] = day.iso.split('-')
    assert.ok(day.quote.includes(day.iso) || day.quote.includes(`${d}/${m}/${y}`), `${day.iso} is not in "${day.quote}"`)
  }
})

test('the title of Operation, "a third of a cent", still describes the cost per safe resolution', () => {
  const cents = figures.sonnetCost.value * 100
  assert.ok(Math.abs(cents - 1 / 3) < 0.05, `${cents} cents is not about a third of a cent: rewrite landing.operation.title`)
  assert.match(es.landing.operation.title, /^Un tercio de centavo de dólar por resolución/)
  assert.match(pt.landing.operation.title, /^Um terço de centavo de dólar por resolução/)
})

test('figures come out in the notation of each language', () => {
  assert.equal(formatNumber(4316, 0, 'es'), '4.316')
  assert.equal(formatNumber(150000, 0, 'pt'), '150.000')
  assert.equal(formatNumber(0.0034, 4, 'es'), '0,0034')
  assert.equal(formatNumber(95, 1, 'pt'), '95,0')
  assert.equal(formatFigure(figures.classifier, 'es'), '84,7')
  assert.equal(formatMillions(figures.transactions, 'es'), '4,4')
  assert.equal(formatDate(liveRunDate.iso, 'es'), '3 de octubre de 2026')
  assert.equal(formatDate(liveRunDate.iso, 'pt'), '3 de outubro de 2026')
  assert.equal(formatShortDate(liveRunDate.iso, 'es'), '03/10/2026')
  assert.equal(formatShortDate(redTeamDate.iso, 'pt'), '30/09/2026')
})
