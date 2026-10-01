// Checks in a real browser, on a phone (390x844), what the demo panel drawer does with a scenario: `node
// ops/demo_drawer_check.mjs <web port> <screenshot dir> [reduced]` (`reduced` runs it with prefers-reduced-motion, where the
// drawer closes at once), against `make serve-fixture` (API on API_PORT) and the web dev server pointed at it (`AGENT_API_URL=http://127.0.0.1:<API_PORT> pnpm --dir web dev --port <web port> --host 127.0.0.1`).
// Needs `playwright-core` (`npm i playwright-core` in a scratch directory, then NODE_PATH=<its node_modules>; `npx playwright-core
// install chromium`). It picks the sixth scenario of the list (a card below the first screen of the drawer) and loads it: the
// drawer must close, the chat must show its first message sent and answered, the focus must be in the chat's input, and nothing
// must be drawn above the list. Reopening the drawer, the card must be inside its visible area with the focus on it, the steps
// visible, Tab and Shift+Tab must go on from it without losing the scroll, and, if the scenario has a second step, its button
// sends it and closes the drawer again. Exits 1 if anything fails.
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const [webPort, outDir, motion] = process.argv.slice(2)
mkdirSync(outDir, { recursive: true })
let failed = false
const check = (ok, what) => { if (!ok) failed = true; console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`) }

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: motion === 'reduced' ? 'reduce' : 'no-preference' })
const page = await ctx.newPage()
await page.goto(`http://127.0.0.1:${webPort}/login`)
await page.waitForLoadState('networkidle')
await page.getByRole('button', { name: 'CLI-FIX0001' }).click()
await page.getByRole('button', { name: /^Ingresar$/ }).click()
await page.waitForURL('**/chat')
await page.waitForLoadState('networkidle')

await page.getByRole('button', { name: 'Demo' }).click()
const drawer = page.locator('#shell-demo')
// By class, not by role: a closed drawer is inert, and a role query does not see inside it.
const card = drawer.locator('article.demo__card').nth(5)
const title = await card.getAttribute('aria-label')
const chat = page.locator('.chat-log')
const inChat = (text) => chat.getByText(text, { exact: true })
const answers = () => card.locator('.demo__ok, .demo__bad')
// Everything waits for its condition, with a limit long enough for a cold dev server (the first message compiles the server functions).
const SLOW = 60000
// The focus comes a frame after the drawer closes.
const inputFocused = () => page.waitForFunction(() => document.activeElement?.tagName === 'TEXTAREA', null, { timeout: SLOW }).then(() => true, () => false)
// A panel that slides is settled when its box stops moving; a chat is settled when its last entry has stopped growing.
const still = async (getBox) => {
  let last = null
  for (let i = 0; i < 100; i++) {
    const box = await getBox()
    if (box && last && box.x === last.x && box.y === last.y && box.height === last.height) return
    last = box
    await page.waitForTimeout(50)
  }
}
const drawerSettled = () => still(() => drawer.boundingBox())
const chatSettled = () => still(() => chat.boundingBox())
const stepButton = (n) => card.getByRole('button', { name: `Enviar paso ${n}` })
await card.scrollIntoViewIfNeeded()
await card.getByRole('button', { name: /^(Cargar|Reiniciar)$/ }).click()

// The first message goes by itself, through the chat's own send: the drawer gives the page back and the focus is in the input.
// includeHidden: the drawer may already be closed (hidden) when this asks.
await card.getByRole('region', { name: 'Pasos del escenario', includeHidden: true }).waitFor({ state: 'attached' })
const turns = await card.locator('.demo__quote').allTextContents()
const say = (quote) => quote.replace(/^“|”$/g, '')
await inChat(say(turns[0])).waitFor()
check(true, `"${title}": its first message is in the chat, sent`)
check(await drawer.evaluate((el) => el.hasAttribute('inert')), 'the drawer closed and is out of reach')
check(await inputFocused(), 'the focus is in the chat input')
check(await page.evaluate(() => document.querySelector('textarea')?.value === ''), 'the input was not written into')
await answers().first().waitFor({ state: 'attached', timeout: SLOW })
check((await answers().count()) === 1, 'the first message was answered, and the card shows it')
await chatSettled()
await page.screenshot({ path: `${outDir}/demo-prearmado-movil-es-1-enviado.png` })

await page.getByRole('button', { name: 'Demo' }).click()
await drawerSettled() // the drawer slides in
const box = await card.boundingBox()
const view = await drawer.boundingBox()
const inside = box && view && box.y >= view.y && box.y + Math.min(box.height, 1) <= view.y + view.height && box.x >= view.x
check(!!inside, `the active card is inside the drawer's visible area (card y=${Math.round(box?.y ?? -1)}, drawer ${Math.round(view?.y ?? -1)}..${Math.round((view?.y ?? 0) + (view?.height ?? 0))})`)
check((await drawer.getByRole('region').first().getAttribute('aria-label')) === 'Escenarios guiados', 'above the list there is still nothing but the scenarios')
const steps = drawer.getByRole('region', { name: 'Pasos del escenario' })
const stepsBox = await steps.boundingBox()
check(!!stepsBox && stepsBox.y >= view.y && stepsBox.y < view.y + view.height, 'its steps are visible')
check(await card.evaluate((el) => document.activeElement === el), 'the focus is on the active card')
check(await drawer.evaluate((el) => !el.hasAttribute('inert') && el.contains(document.activeElement)), 'the focus is inside the open drawer')
await page.screenshot({ path: `${outDir}/demo-prearmado-movil-es-2-reabrir-en-tarjeta.png` })

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
await drawerSettled()
await page.keyboard.press('Shift+Tab')
check(await page.evaluate(() => { const a = document.activeElement; return !!a && a.tagName === 'BUTTON' && a.getAttribute('aria-label') !== 'Cerrar' && !!a.closest('article') }), 'Shift+Tab from the card goes to the control of the scenario above it')

// The next step is sent with a click on its card; the drawer closes over the chat and the answer comes there.
if (turns.length > 1) {
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Demo' }).click()
  await drawerSettled()
  await stepButton(2).scrollIntoViewIfNeeded()
  check(await stepButton(2).isEnabled(), 'the button of step 2 is on its card, enabled')
  await stepButton(2).click()
  await inChat(say(turns[1])).waitFor()
  check(true, 'step 2 is in the chat, sent')
  check(await drawer.evaluate((el) => el.hasAttribute('inert')), 'the drawer closed again')
  check(await inputFocused(), 'the focus is in the chat input')
  await answers().nth(1).waitFor({ state: 'attached', timeout: SLOW })
  await chatSettled()
  await page.screenshot({ path: `${outDir}/demo-prearmado-movil-es-3-paso-enviado.png` })
} else {
  console.log('note the scenario has one step: no second step to send')
}

await browser.close()
process.exit(failed ? 1 : 0)
