// HTTP tests against the production build (dist/server/server.js): the same request handler `vite build` produces,
// called with real Request objects, in front of a fake agent API. `pnpm test:http` builds first.
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

export const ADMIN = 'admin-key-0123456789-abcdefgh'
export const ANA = 'ana-key-0123456789-abcdefghij'
export const ORIGIN = 'http://console.test'

type Handler = { fetch(request: Request): Promise<Response> }

export async function startConsole() {
  const api: Server = createServer((req, res) => {
    const reply = (status: number, body: unknown) => {
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(body))
    }
    const admin = req.headers['x-admin-key'] === ADMIN
    const operator = req.headers['x-operator-key'] === ANA
    if (req.url?.startsWith('/admin/operator/me')) return operator ? reply(200, { operator: 'ana' }) : reply(401, { detail: 'invalid operator key' })
    if (req.url?.startsWith('/admin/')) return admin ? reply(200, req.url.startsWith('/admin/human_queue') ? [] : {}) : reply(401, { detail: 'invalid admin key' })
    reply(404, {})
  })
  await new Promise<void>((done) => api.listen(0, '127.0.0.1', done))
  process.env.AGENT_API_URL = `http://127.0.0.1:${(api.address() as AddressInfo).port}`
  process.env.NODE_ENV = 'production'
  const built = (await import(pathToFileURL(join(import.meta.dirname, '../../dist/server/server.js')).href)) as { default: Handler }

  const send = (path: string, init: { method?: string; fields?: Record<string, string>; headers?: Record<string, string> } = {}) => {
    const headers = new Headers(init.headers)
    let body: string | undefined
    if (init.fields) {
      body = new URLSearchParams(init.fields).toString()
      headers.set('Content-Type', 'application/x-www-form-urlencoded')
    }
    return built.default.fetch(new Request(`${ORIGIN}${path}`, { method: init.method ?? (init.fields ? 'POST' : 'GET'), headers, body, redirect: 'manual' }))
  }
  return { send, close: () => api.close() }
}

/** What a browser submitting the console's own form sends. */
export const SAME_ORIGIN = { Origin: ORIGIN, Referer: `${ORIGIN}/operador/login`, 'Sec-Fetch-Site': 'same-origin' }
export const CROSS_SITE = { Origin: 'https://attacker.invalid', Referer: 'https://attacker.invalid/x', 'Sec-Fetch-Site': 'cross-site' }

/** The session cookie a response sets, as `name=value`, or null. The flash cookie is not a session. */
export function sessionCookie(response: Response) {
  const set = response.headers.getSetCookie().find((c) => /cecilai_operator=/.test(c) && !/flash/.test(c) && !/=;|Max-Age=0|Expires=Thu, 01 Jan 1970/i.test(c))
  return set ? set.split(';')[0] : null
}

export const setCookies = (response: Response) => response.headers.getSetCookie()

/** Whether this cookie still opens the console: a page behind the login answers 200, not a redirect. */
export async function opensConsole(app: { send: Awaited<ReturnType<typeof startConsole>>['send'] }, cookie: string) {
  const page = await app.send('/operador/cola', { headers: { Cookie: cookie } })
  return page.status === 200
}
