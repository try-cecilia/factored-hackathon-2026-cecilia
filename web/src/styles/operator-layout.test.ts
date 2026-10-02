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

// Seen at 360 px: the queue was a 760 px table scrolling sideways, and the request, the one column that says what the case is about,
// started off the screen. On a phone each case is a card: the request takes a whole line, the headers stay as sort buttons.
test('on a phone the queue is a list of cards with the request on its own line', () => {
  const start = css.indexOf('@media (max-width: 700px) {')
  assert.ok(start >= 0, 'the phone layout of the queue is there')
  const phone = css.slice(start, css.indexOf('\n}', start))
  assert.match(phone, /\.op-table--queue \.ui-dt__table\s*\{[^}]*min-width:\s*0/)
  assert.match(phone, /\.op-table--queue \.ui-dt__row\s*\{[^}]*display:\s*flex;[^}]*flex-wrap:\s*wrap/)
  assert.match(phone, /\[data-col='request'\]\s*\{[^}]*flex-basis:\s*100%/)
  assert.doesNotMatch(phone, /thead[^{]*\{[^}]*display:\s*none/, 'the sort buttons stay reachable')
})

// Seen at 844x390 (a phone on its side): a fixed head and foot left 200 px of case between them. There the whole case scrolls as one
// page and the actions stay pinned at the bottom.
test('on a short screen the case scrolls as one page, with its actions pinned at the bottom', () => {
  const start = css.indexOf('@media (max-width: 1100px) and (max-height: 500px) {')
  assert.ok(start >= 0, 'the short-screen layout is there')
  const short = css.slice(start, css.indexOf('\n}', start))
  assert.match(short, /\.op-ticket__body[^{]*\{[^}]*overflow:\s*visible/)
  assert.match(short, /\.op-ticket__foot\s*\{[^}]*position:\s*sticky;[^}]*bottom:\s*0/)
})
