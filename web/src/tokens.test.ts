import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const declared = (name: string) => new RegExp(`^\\s*${name}:\\s*\\S`, 'm').test(css)

// Names the approved design uses (Paper get_tokens, format css). If a screen needs a new one, it goes in Paper first.
const paper = [
  '--color-fill-subtle', '--color-fill-muted', '--color-fill-strong',
  '--color-sky-100', '--color-sky-300', '--color-sky-500', '--color-sky-700', '--color-sky-900',
  '--color-cecil-blue', '--color-success', '--color-danger', '--color-caution', '--color-warning',
  '--color-line', '--color-row-hover', '--color-row-selected', '--color-ink-hover',
  '--radius-control', '--radius-compact',
  '--text-compact-2xs', '--text-compact-xs', '--text-compact-sm', '--text-compact-md', '--text-compact-lg', '--text-compact-xl',
  '--spacing-compact-1', '--spacing-compact-2', '--spacing-compact-3', '--spacing-compact-4',
]

// Names that existed before the UI kit and that the screens written then still use.
const legacy = ['--color-sun-amber', '--color-sun-yellow', '--color-sun-orange', '--color-sun-ember', '--color-ink-muted', '--color-ink-soft', '--hairline', '--hairline-strong', '--focus-ring', '--shadow-window', '--sun']

test('tokens.css declares every token of the approved design', () => {
  for (const name of paper) assert.ok(declared(name), name)
})

test('tokens.css keeps the names of the screens that predate the UI kit', () => {
  for (const name of legacy) assert.ok(declared(name), name)
})

test('the fill tokens are the 4%, 8% and 12% tones of the design', () => {
  assert.match(css, /--color-fill-subtle:\s*#0000000A/)
  assert.match(css, /--color-fill-muted:\s*#00000014/)
  assert.match(css, /--color-fill-strong:\s*#0000001F/)
})
