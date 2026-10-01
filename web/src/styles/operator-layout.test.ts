import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

// The jsdom tests do not process CSS, so the one rule that keeps the queue's header and filter strip from being squeezed over the table
// is held here. Seen at 1440x900 with 25 rows and a case open: the list is a scrolling flex column, its rows shrank to the window's height,
// and a filter strip that had wrapped spilled over "Prioridad" and "Operador" (docs/demo/operador-cola-06-*.png shows it fixed).
const css = readFileSync(new URL('./operator.css', import.meta.url), 'utf8')

test('the rows of the queue list do not shrink inside the scrolling column', () => {
  assert.match(css, /\.op-list\s*>\s*\*\s*\{[^}]*flex-shrink:\s*0/)
  assert.match(css, /\.op-list\s*\{[^}]*flex-direction:\s*column[^}]*overflow:\s*auto/)
})
