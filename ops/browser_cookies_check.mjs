// Logs in through real browsers against a running stack, to check that the session cookies survive: `node ops/browser_cookies_check.mjs
// <http|https> <web port> <screenshot dir>`, with ADMIN (the read key) and OPERATOR (an operator key) in the environment.
// Needs `playwright-core` (`npm i playwright-core` in a scratch directory; `npx playwright-core install webkit chromium`) and the stack
// from `docker compose -p <a throwaway project> -f ops/docker-compose.yml --env-file <a bootstrap_env.py --free-ports file> up --wait`.
//  - `http`: the compose's default origin. Customer and operator login through 127.0.0.1 and through localhost, in WebKit (Safari's
//    engine) and Chromium; then the same with the browser refusing the cookie (the page must say so, not hang); then a form posted
//    from an origin the console does not trust (back to the login, with the origins to use).
//  - `https`: restart the web first with WEB_PUBLIC_ORIGIN=https://console.verify.example while the browser stays on http: the old
//    behavior (Secure __Host- cookies over http), which WebKit drops and Chromium keeps.
import { webkit, chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'

const [mode, webPort, outDir] = process.argv.slice(2)
const { ADMIN, OPERATOR } = process.env
mkdirSync(outDir, { recursive: true })
const engines = { webkit, chromium }
const results = []
const log = (ok, what) => { results.push(ok); console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`) }
const cookieNames = async (ctx) => (await ctx.cookies()).map((c) => `${c.name}${c.secure ? '(Secure)' : ''}`).join(', ') || '(none)'

async function customer(engine, host, { strip = false, shot }) {
  const browser = await engines[engine].launch()
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 760 } })
  const page = await ctx.newPage()
  // A browser that refuses the cookie: the request goes out by Node's own fetch (its cookie jar is not the browser's) and the
  // response comes back without its Set-Cookie
  if (strip) await ctx.route('**/_serverFn/**', async (route) => {
    const req = route.request()
    const res = await fetch(req.url(), { method: req.method(), headers: await req.allHeaders(), body: req.postDataBuffer() ?? undefined, redirect: 'manual' })
    const headers = Object.fromEntries([...res.headers].filter(([k]) => k !== 'set-cookie'))
    await route.fulfill({ status: res.status, headers, body: Buffer.from(await res.arrayBuffer()) })
  })
  const base = `http://${host}:${webPort}`
  await page.goto(`${base}/login`)
  await page.getByRole('button', { name: /^CLI-/ }).first().click()
  await page.getByRole('button', { name: /^Ingresar$/ }).click()
  await page.waitForTimeout(3000)
  const landed = new URL(page.url()).pathname === '/chat'
  const cookies = await cookieNames(ctx)
  if (shot) await page.screenshot({ path: `${outDir}/${shot}.png` })
  const btn = await page.getByRole('button', { name: /^(Ingresar|Ingresando…)$/ }).count() ? await page.getByRole('button', { name: /^(Ingresar|Ingresando…)$/ }).first().innerText() : null
  const alert = await page.getByRole('alert').first().innerText().catch(() => null)
  await browser.close()
  return { landed, cookies, btn, alert }
}

async function operator(engine, host, { strip = false, foreignOrigin = false, shot }) {
  const browser = await engines[engine].launch()
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 760 } })
  const page = await ctx.newPage()
  // The same for the login form: the browser follows the 303 but never got the cookie (a meta refresh stands for the redirect)
  if (strip) await ctx.route('**/operador/sesion', async (route) => {
    const req = route.request()
    const res = await fetch(req.url(), { method: 'POST', headers: await req.allHeaders(), body: req.postDataBuffer() ?? undefined, redirect: 'manual' })
    const to = res.headers.get('location')
    await route.fulfill({ status: 200, contentType: 'text/html', body: `<meta http-equiv="refresh" content="0;url=${to}">` })
  })
  // A form that claims to come from a page of another origin (what the check exists to refuse)
  if (foreignOrigin) await ctx.route('**/operador/sesion', async (route) => {
    const req = route.request()
    const res = await fetch(req.url(), { method: 'POST', headers: { ...(await req.allHeaders()), origin: 'http://192.168.1.20:3000', referer: 'http://192.168.1.20:3000/operador/login' }, body: req.postDataBuffer() ?? undefined, redirect: 'manual' })
    await route.fulfill({ status: 200, contentType: 'text/html', body: `<meta http-equiv="refresh" content="0;url=${res.headers.get('location')}">` })
  })
  const base = `http://${host}:${webPort}`
  await page.goto(`${base}/operador/login`)
  await page.locator('input[name=admin_key]').fill(ADMIN)
  await page.locator('input[name=operator_key]').fill(OPERATOR)
  await page.getByRole('button', { name: /^Ingresar$/ }).click()
  await page.waitForTimeout(3000)
  const landed = new URL(page.url()).pathname === '/operador/cola'
  const cookies = await cookieNames(ctx)
  if (shot) await page.screenshot({ path: `${outDir}/${shot}.png` })
  const alert = await page.getByRole('alert').first().innerText().catch(() => null)
  await browser.close()
  return { landed, cookies, alert, url: page.url() }
}

if (mode === 'http') {
  for (const engine of ['webkit', 'chromium']) for (const host of ['127.0.0.1', 'localhost']) {
    const c = await customer(engine, host, { shot: `cookies-http-${engine}-${host === 'localhost' ? 'localhost' : 'ip'}-cliente-chat` })
    log(c.landed, `${engine} ${host} cliente: login -> /chat; cookies: ${c.cookies}`)
    const o = await operator(engine, host, { shot: `cookies-http-${engine}-${host === 'localhost' ? 'localhost' : 'ip'}-operador-cola` })
    log(o.landed, `${engine} ${host} operador: login -> /operador/cola; cookies: ${o.cookies}`)
  }
  // The browser refuses the session (Set-Cookie dropped): the buttons come back and say why
  for (const engine of ['webkit', 'chromium']) {
    const c = await customer(engine, '127.0.0.1', { strip: true, shot: `cookies-sin-sesion-${engine}-cliente` })
    log(!c.landed && c.btn === 'Ingresar' && /no guardó la sesión/.test(c.alert ?? ''), `${engine} cliente sin cookie: se queda en /login, botón "${c.btn}", aviso: ${c.alert}`)
    const o = await operator(engine, '127.0.0.1', { strip: true, shot: `cookies-sin-sesion-${engine}-operador` })
    log(!o.landed && /no guardó la sesión/.test(o.alert ?? ''), `${engine} operador sin cookie: vuelve al login, aviso: ${o.alert}`)
  }
  // A refused origin no longer leaves a blank "Forbidden": back to the login, with the origins to use
  for (const engine of ['webkit', 'chromium']) {
    const o = await operator(engine, 'localhost', { foreignOrigin: true, shot: `origen-rechazado-${engine}-operador` })
    log(!o.landed && new URL(o.url).pathname === '/operador/login' && /Ingresar desde http:\/\/127\.0\.0\.1:\d+, http:\/\/localhost:\d+\./.test(o.alert ?? ''), `${engine} operador, origen ajeno: ${o.url} aviso: ${o.alert}`)
  }
} else {
  // The web declares an https origin but the browser is on plain http (the old behavior of the image): Secure __Host- cookies
  for (const engine of ['webkit', 'chromium']) {
    const c = await customer(engine, '127.0.0.1', { shot: `cookies-https-config-http-${engine}-cliente` })
    // The refusal's notice rides in the URL: WebKit, which dropped the Secure cookie above, still shows it
    const o = await operator(engine, '127.0.0.1', { shot: `origen-rechazado-https-config-${engine}-operador` })
    log(!o.landed && /No pudimos verificar el origen del formulario\. Ingresar desde https:\/\/console\.verify\.example\./.test(o.alert ?? ''), `${engine} operador con origen configurado https, visto por http: ${o.alert}`)
    log(engine === 'chromium' ? true : !c.landed && c.btn === 'Ingresar' && /no guardó la sesión/.test(c.alert ?? ''), `${engine} cliente con cookie Secure por http: landed=${c.landed} botón="${c.btn}" aviso=${c.alert} cookies=${c.cookies}`)
  }
}
process.exit(results.every(Boolean) ? 0 : 1)
