import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

// What keeps the customer app usable on a phone, held here because the jsdom tests do not process CSS. Seen on an iPhone and on
// Android: a field under 16px makes iOS zoom in on focus and stay zoomed; 100vh is taller than the screen under the browser's bars;
// a phone with a notch draws over the bar and the composer unless the page pads the safe area.
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const src = fileURLToPath(new URL('..', import.meta.url))
const cssFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? cssFiles(path) : name.endsWith('.css') ? [path] : []
  })
// The body of the first `@media <query> {` block, up to its closing brace.
const media = (css: string, query: string) => {
  const start = css.indexOf(`@media ${query} {`)
  assert.ok(start >= 0, `@media ${query} is there`)
  let depth = 0
  for (let i = css.indexOf('{', start); i < css.length; i++) {
    if (css[i] === '{') depth++
    if (css[i] === '}' && --depth === 0) return css.slice(start, i)
  }
  throw new Error(`@media ${query} is not closed`)
}

test('the viewport hands the safe areas to the page and lets the keyboard shrink the layout', () => {
  const root = read('../routes/__root.tsx')
  const viewport = root.match(/name: 'viewport', content: '([^']*)'/)
  assert.ok(viewport, 'the root sets a viewport')
  assert.match(viewport[1], /viewport-fit=cover/)
  assert.match(viewport[1], /interactive-widget=resizes-content/)
})

test('no stylesheet sizes anything to 100vh: the screen under the browser bars is 100dvh', () => {
  for (const file of cssFiles(src)) assert.doesNotMatch(readFileSync(file, 'utf8'), /\b100vh\b/, file)
})

test('on a touch screen every field is at least 16px, so iOS never zooms in on it', () => {
  const block = media(read('../styles.css'), '(pointer: coarse)')
  assert.match(block, /input[^{]*,\s*textarea,\s*select\s*\{[^}]*font-size:\s*max\(16px,[^}]*!important/)
})

test('on a touch screen buttons, quick replies and the send button are 44px targets', () => {
  assert.match(media(read('../ui/Button.css'), '(pointer: coarse)'), /\.ui-btn\s*\{[^}]*min-height:\s*44px/)
  assert.match(media(read('../ui/messages/QuickReplies.css'), '(pointer: coarse)'), /\.ui-quick__chip\s*\{[^}]*min-height:\s*44px/)
  assert.match(media(read('../chat/chat.css'), '(pointer: coarse)'), /\.composer \.ui-btn\s*\{[^}]*width:\s*44px;\s*height:\s*44px/)
})

test('a quick reply longer than the line wraps inside its chip instead of running off the screen', () => {
  const chip = read('../ui/messages/QuickReplies.css').match(/\.ui-quick__chip\s*\{([^}]*)\}/)
  assert.ok(chip)
  assert.match(chip[1], /min-height:\s*30px/)
  assert.doesNotMatch(chip[1], /(?:^|[\s;])height:/)
  assert.match(chip[1], /max-width:\s*100%/)
})

test('the composer and the drawers stay clear of the notch and the home indicator', () => {
  assert.match(read('../chat/chat.css'), /\.chat__foot\s*\{[^}]*padding:[^;}]*env\(safe-area-inset-bottom\)/)
  const shell = read('./AppShell.css')
  assert.match(shell, /\.shell\s*\{[^}]*padding-top:\s*env\(safe-area-inset-top\)/)
  for (const drawer of ['.shell__demo, .shell__demo[inert]', '.shell__case']) {
    const start = shell.indexOf(`${drawer} {`)
    assert.ok(start >= 0, drawer)
    assert.match(shell.slice(start, shell.indexOf('}', start)), /env\(safe-area-inset-top\)[^;]*env\(safe-area-inset-bottom\)/, drawer)
  }
})
