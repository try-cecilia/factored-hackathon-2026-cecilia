// Checks in a real browser, on a phone (390x844), that the demo panel drawer reopens on the scenario in course: `node
// ops/demo_drawer_check.mjs <web port> <screenshot dir>`, against `make serve-fixture` (API on API_PORT) and the web dev server
// pointed at it (`AGENT_API_URL=http://127.0.0.1:<API_PORT> pnpm --dir web dev --port <web port>`).
// Needs `playwright-core` (`npm i playwright-core` in a scratch directory, then NODE_PATH=<its node_modules>; `npx playwright-core
// install chromium`). It picks the sixth scenario of the list (a card below the first screen of the drawer), loads it, sends nothing,
// and reopens the drawer: the card must be inside the drawer's visible area, the focus must be on it (inside the drawer), and the
// steps must be visible. Exits 1 if anything fails.
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const [webPort, outDir] = process.argv.slice(2)
mkdirSync(outDir, { recursive: true })
let failed = false
const check = (ok, what) => { if (!ok) failed = true; console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`) }

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
const page = await ctx.newPage()
await page.goto(`http://127.0.0.1:${webPort}/login`)
await page.waitForLoadState('networkidle')
await page.getByRole('button', { name: 'CLI-FIX0001' }).click()
await page.getByRole('button', { name: /^Ingresar$/ }).click()
await page.waitForURL('**/chat')
await page.waitForLoadState('networkidle')

await page.getByRole('button', { name: 'Demo' }).click()
const drawer = page.locator('#shell-demo')
const cards = drawer.getByRole('article')
const card = cards.nth(5)
const title = await card.getAttribute('aria-label')
await card.scrollIntoViewIfNeeded()
await card.getByRole('button').first().click()
await page.waitForFunction(() => document.querySelector('textarea')?.value.length > 0)
check(await page.evaluate(() => document.activeElement?.tagName === 'TEXTAREA'), `"${title}": the input holds its message and has the focus`)
check(await drawer.evaluate((el) => el.hasAttribute('inert')), 'the drawer closed and is out of reach')

await page.getByRole('button', { name: 'Demo' }).click()
await page.waitForTimeout(500) // the drawer slides in
const box = await card.boundingBox()
const view = await drawer.boundingBox()
const inside = box && view && box.y >= view.y && box.y + Math.min(box.height, 1) <= view.y + view.height && box.x >= view.x
check(!!inside, `the active card is inside the drawer's visible area (card y=${Math.round(box?.y ?? -1)}, drawer ${Math.round(view?.y ?? -1)}..${Math.round((view?.y ?? 0) + (view?.height ?? 0))})`)
const steps = drawer.getByRole('region', { name: 'Pasos del escenario' })
const stepsBox = await steps.boundingBox()
check(!!stepsBox && stepsBox.y >= view.y && stepsBox.y < view.y + view.height, 'its steps are visible')
check(await card.evaluate((el) => document.activeElement === el), 'the focus is on the active card')
check(await drawer.evaluate((el) => !el.hasAttribute('inert') && el.contains(document.activeElement)), 'the focus is inside the open drawer')
await page.screenshot({ path: `${outDir}/demo-prearmado-movil-es-4-reabrir-en-tarjeta.png` })

// Tab from the card goes on to the first control inside it, and the drawer keeps its scroll (it does not jump back to the head).
const scrollOf = () => drawer.evaluate((el) => { let p = el; while (p && p.scrollHeight <= p.clientHeight) p = p.parentElement; return p ? p.scrollTop : 0 })
const scrolled = await scrollOf()
await page.keyboard.press('Tab')
check(await card.evaluate((el) => el !== document.activeElement && el.contains(document.activeElement)), 'Tab from the card lands on a control inside the card')
check(Math.abs((await scrollOf()) - scrolled) < 2 && scrolled > 0, `the drawer keeps its scroll (${scrolled} -> ${await scrollOf()})`)
const after = await card.boundingBox()
check(!!after && after.y >= view.y && after.y < view.y + view.height, 'the card is still in view')
// Shift+Tab from the card (on a fresh reopening) goes to the control before it, not to the last of the drawer.
await page.keyboard.press('Escape')
await page.getByRole('button', { name: 'Demo' }).click()
await page.waitForTimeout(500)
await page.keyboard.press('Shift+Tab')
check(await page.evaluate(() => { const a = document.activeElement; return !!a && a.tagName === 'BUTTON' && a.getAttribute('aria-label') !== 'Cerrar' && !!a.closest('article') }), 'Shift+Tab from the card goes to the control of the scenario above it')

await browser.close()
process.exit(failed ? 1 : 0)
