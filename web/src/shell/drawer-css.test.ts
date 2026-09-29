import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

// A control inside a `visibility: hidden` panel cannot take the focus. The drawers focus their first control the moment they open,
// so the open state must be visible from the first frame (a 0s visibility transition) and only hide after the slide when closing.
// Chromium at 153 leaves the focus on <body> otherwise, unless the reader asked for reduced motion.
const css = readFileSync(new URL('./AppShell.css', import.meta.url), 'utf8')
const rule = (selector: string) => {
  const start = css.indexOf(`${selector} {`)
  assert.ok(start >= 0, `${selector} has a rule`)
  return css.slice(start, css.indexOf('}', start))
}

test('an open drawer is visible from its first frame, so its first control can take the focus', () => {
  for (const selector of [".shell[data-menu='open'] .shell__side", ".shell[data-demo='open'] .shell__demo", ".shell[data-case='open'] .shell__case"]) {
    const block = rule(selector)
    assert.match(block, /visibility:\s*visible/, selector)
    assert.match(block, /transition:[^;]*visibility 0s(?![^;]*\d)/, `${selector} shows without waiting for the slide`)
  }
})

test('a closing drawer stays visible until the slide ends, then hides', () => {
  for (const selector of ['.shell__side', '.shell__demo, .shell__demo[inert]', '.shell__case']) {
    const media = css.slice(css.indexOf('@media'))
    const block = media.slice(media.indexOf(`${selector} {`), media.indexOf('}', media.indexOf(`${selector} {`)))
    assert.match(block, /transition:[^;]*visibility 0s linear 0\.18s/, selector)
  }
})
