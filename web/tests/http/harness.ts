// HTTP tests against the production build (dist/server/server.js): the same request handler `vite build` produces,
// called with real Request objects, in front of a fake agent API. `pnpm test:http` builds first.
import assert from 'node:assert/strict'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

export const ADMIN = 'admin-key-0123456789-abcdefgh'
export const ANA = 'ana-key-0123456789-abcdefghij'
export const ORIGIN = 'http://console.test'

type Handler = { fetch(request: Request): Promise<Response> }

type ApiMode = 'ok' | 'revoked' | 'forbidden' | 'error'
type Gate = { reached: Promise<void>; release: (status?: number) => void }

export async function startConsole() {
  // What the fake agent API does next: a mode for every admin read, and an optional gate that holds one queue read
  // until the test releases it (a slow response that arrives after other things have happened).
  let mode: ApiMode = 'ok'
  let pending: { onReach: () => void; released: Promise<number> } | null = null
  const api: Server = createServer(async (req, res) => {
    const reply = (status: number, body: unknown) => {
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(body))
    }
    const admin = req.headers['x-admin-key'] === ADMIN
    const operator = req.headers['x-operator-key'] === ANA
    if (req.url?.startsWith('/admin/operator/me')) return operator ? reply(200, { operator: 'ana' }) : reply(401, { detail: 'invalid operator key' })
    if (req.url?.startsWith('/admin/human_queue') && pending) {
      const gate = pending
      pending = null
      gate.onReach()
      const status = await gate.released
      return status === 200 ? reply(200, []) : reply(status, { detail: 'held response' })
    }
    if (req.url?.startsWith('/admin/') && mode !== 'ok') return reply({ revoked: 401, forbidden: 403, error: 500 }[mode], { detail: mode })
    if (req.url?.startsWith('/admin/')) return admin ? reply(200, req.url.startsWith('/admin/human_queue') ? [] : {}) : reply(401, { detail: 'invalid admin key' })
    reply(404, {})
  })
  await new Promise<void>((done) => api.listen(0, '127.0.0.1', done))
  process.env.AGENT_API_URL = `http://127.0.0.1:${(api.address() as AddressInfo).port}`
  process.env.NODE_ENV = 'production'
  process.env.WEB_PUBLIC_ORIGIN = ORIGIN // required in production: the origin the browser sees, never derived from proxy headers
  const built = (await import(pathToFileURL(join(import.meta.dirname, '../../dist/server/server.js')).href)) as { default: Handler }

  const send = (path: string, init: { method?: string; fields?: Record<string, string>; headers?: Record<string, string>; base?: string } = {}) => {
    const headers = new Headers(init.headers)
    let body: string | undefined
    if (init.fields) {
      body = new URLSearchParams(init.fields).toString()
      headers.set('Content-Type', 'application/x-www-form-urlencoded')
    }
    return built.default.fetch(new Request(`${init.base ?? ORIGIN}${path}`, { method: init.method ?? (init.fields ? 'POST' : 'GET'), headers, body, redirect: 'manual' }))
  }
  const hold = (): Gate => {
    let release!: (status?: number) => void
    let reached!: () => void
    const released = new Promise<number>((done) => (release = (status = 200) => done(status)))
    const arrived = new Promise<void>((done) => (reached = done))
    pending = { onReach: reached, released }
    return { reached: arrived, release }
  }
  return { send, hold, setApi: (next: ApiMode) => void (mode = next), close: () => api.close() }
}

/** What a browser submitting the console's own form sends. */
export const SAME_ORIGIN = { Origin: ORIGIN, Referer: `${ORIGIN}/operador/login`, 'Sec-Fetch-Site': 'same-origin' }
export const CROSS_SITE = { Origin: 'https://attacker.invalid', Referer: 'https://attacker.invalid/x', 'Sec-Fetch-Site': 'cross-site' }

/** The session cookie a response sets, as `name=value`, or null. The flash cookie is not a session. */
export function sessionCookie(response: Response) {
  const set = response.headers.getSetCookie().find((c) => /cecilai_operator=/.test(c) && !/flash/.test(c) && !/=;|Max-Age=0|Expires=Thu, 01 Jan 1970/i.test(c))
  return set ? set.split(';')[0] : null
}

/** A refused form post: back to the login with a fixed reason in the URL (never a bare 403), and no cookie at all. */
export function assertRefused(response: Response, motivo: 'origen' | 'origen-config', note = '') {
  assert.equal(response.status, 303, note)
  assert.equal(response.headers.get('location'), `/operador/login?motivo=${motivo}`, note)
  assert.deepEqual(response.headers.getSetCookie(), [], note)
}

/** The text of the alert a rendered page shows, or null. The page also carries its dictionaries as data, so a text being anywhere in the HTML proves nothing. */
export const alertOf = (html: string) => /role="alert">([^<]*)</.exec(html)?.[1] ?? null

export const setCookies = (response: Response) => response.headers.getSetCookie()

/** Whether this cookie still opens the console: a page behind the login answers 200, not a redirect. */
export async function opensConsole(app: { send: Awaited<ReturnType<typeof startConsole>>['send'] }, cookie: string) {
  const page = await app.send('/operador/cola', { headers: { Cookie: cookie } })
  return page.status === 200
}

/** A browser's cookie jar, enough for these tests: applies Set-Cookie headers in the order responses arrive. */
export function cookieJar() {
  const jar = new Map<string, string>()
  return {
    apply(response: Response) {
      for (const line of response.headers.getSetCookie()) {
        const [pair, ...attributes] = line.split(';').map((part) => part.trim())
        const at = pair.indexOf('=')
        const name = pair.slice(0, at)
        const gone = attributes.some((a) => /^max-age=0$/i.test(a) || /^expires=.*1970/i.test(a))
        if (gone || at === pair.length - 1) jar.delete(name)
        else jar.set(name, pair.slice(at + 1))
      }
    },
    /** The session cookie as `name=value`, or null (the flash cookie is not a session). */
    session() {
      const found = [...jar].find(([name]) => /cecilai_operator$/.test(name))
      return found ? `${found[0]}=${found[1]}` : null
    },
    header() {
      return [...jar].map(([name, value]) => `${name}=${value}`).join('; ')
    },
  }
}
