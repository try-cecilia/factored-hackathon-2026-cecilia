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

// Seen at 390 px: opening "Evidencia" (a table that needed 440 px) made the whole detail 488 px wide, and the version, the close button, the
// summaries of the sections and "Copiar resumen" fell off the screen. A flex item does not shrink below its content unless it says so, so
// every step of the chain from the detail down must be able to shrink. (Evidence is now a list of two-line rows, with no width of its own.)
test('the detail can shrink below the width of whatever it holds', () => {
  for (const rule of ['.op-detail', '.op-ticket', '.op-ticket__body']) {
    const block = css.match(new RegExp(`(?:^|\\n)${rule.replace('.', '\\.')}\\s*\\{([^}]*)\\}`))
    assert.ok(block, `${rule} has a rule`)
    assert.match(block[1], /min-width:\s*0/, `${rule} can shrink`)
  }
})
