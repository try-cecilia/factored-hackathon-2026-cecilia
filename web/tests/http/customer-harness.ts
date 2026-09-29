// The customer app against the production build, in front of a fake agent API. Like harness.ts, but for the customer side:
// the fake answers /auth/session, /chat/history and the demo endpoints the way api/main.py does.
import { createServer, type IncomingMessage, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'

export const ORIGIN = 'http://app.test'
export const TOKEN = 'tok-secret-0123456789abcdef'

type Handler = { fetch(request: Request): Promise<Response> }
export type FakeApi = (req: IncomingMessage, reply: (status: number, body: unknown) => void) => boolean | void

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
  return { get, seen, close: () => api.close() }
}
