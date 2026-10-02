// The customer app against the production build, in front of a fake agent API. Like harness.ts, but for the customer side:
// the fake answers /auth/session, /chat/history and the demo endpoints the way api/main.py does.
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { createServer, type IncomingMessage, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

export const ORIGIN = 'http://app.test'
export const TOKEN = 'tok-secret-0123456789abcdef'

type Handler = { fetch(request: Request): Promise<Response> }
export type FakeApi = (req: IncomingMessage, reply: (status: number, body: unknown) => void) => boolean | void

// { data: { customer_id: 'CLI-FIX0001', pin: '123456' }, context: {} } as the framework's serializer (seroval) writes it.
const SIGN_IN_BODY =
  '{"t":{"t":10,"i":0,"p":{"k":["data","context"],"v":[{"t":10,"i":1,"p":{"k":["customer_id","pin"],"v":[{"t":1,"s":"CLI-FIX0001"},{"t":1,"s":"123456"}]},"o":0},{"t":10,"i":2,"p":{"k":[],"v":[]},"o":0}]},"o":0},"f":127,"m":[]}'

export const session = { customer_id: 'CLI-FIX0001', session_ref: 'ref-1', segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }

export async function startCustomerApp(fake: FakeApi) {
  const seen: { url: string; token: string | undefined }[] = []
  const api: Server = createServer((req, res) => {
    const reply = (status: number, body: unknown) => {
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(body))
    }
    seen.push({ url: req.url ?? '', token: req.headers['x-session-token'] as string | undefined })
    const live = req.headers['x-session-token'] === TOKEN
    if (req.url === '/auth/session' && req.method === 'POST') return reply(200, { token: TOKEN, expires_in: 900 })
    if (req.url === '/auth/session') return live ? reply(200, session) : reply(401, { detail: 'invalid or expired session' })
    if (fake(req, reply) !== false) return
    reply(404, { detail: 'Not Found' })
  })
  await new Promise<void>((done) => api.listen(0, '127.0.0.1', done))
  process.env.AGENT_API_URL = `http://127.0.0.1:${(api.address() as AddressInfo).port}`
  process.env.NODE_ENV = 'production'
  process.env.WEB_PUBLIC_ORIGIN = ORIGIN
  const built = (await import(pathToFileURL(join(import.meta.dirname, '../../dist/server/server.js')).href)) as { default: Handler }
  const get = (path: string, headers: Record<string, string> = {}) =>
    built.default.fetch(new Request(`${ORIGIN}${path}`, { headers, redirect: 'manual' }))
  // The sign-in server function, called the way the browser calls it: its id is read from the build, not written here.
  // `proof` is what the browser says about where the call came from; the default is a call from the app's own page.
  const signIn = async (base = ORIGIN, proof: Record<string, string> = { Origin: base, 'Sec-Fetch-Site': 'same-origin' }) => {
    const assets = join(import.meta.dirname, '../../dist/server/assets')
    const file = readdirSync(assets).find((f) => f.startsWith('auth.functions-') && readFileSync(join(assets, f), 'utf8').includes('name: "login"'))
    const id = /id: "([0-9a-f]+)",\s*name: "login"/.exec(readFileSync(join(assets, file ?? ''), 'utf8'))?.[1]
    assert.ok(id, 'the login server function is in the build')
    return built.default.fetch(
      new Request(`${base}/_serverFn/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-tsr-serverFn': 'true', Accept: 'application/json', ...proof },
        body: SIGN_IN_BODY,
      }),
    )
  }
  return { get, signIn, seen, close: () => api.close() }
}
