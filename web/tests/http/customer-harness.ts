// The customer app against the production build, in front of a fake agent API. Like harness.ts, but for the customer side:
// the fake answers /auth/session, /chat/history and the demo endpoints the way api/main.py does.
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { createServer, type IncomingMessage, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { pathToFileURL } from 'node:url'
import { join } from 'node:path'
import { rpcRequest, within, type RpcInit } from './rpc.ts'

export const ORIGIN = 'http://app.test'
export const TOKEN = 'tok-secret-0123456789abcdef'

type Handler = { fetch(request: Request): Promise<Response> }
export type FakeApi = (req: IncomingMessage, reply: (status: number, body: unknown) => void) => boolean | void

// { data: { customer_id: 'CLI-FIX0001', pin: '123456' }, context: {} } as the framework's serializer (seroval) writes it.
const SIGN_IN_BODY =
  '{"t":{"t":10,"i":0,"p":{"k":["data","context"],"v":[{"t":10,"i":1,"p":{"k":["customer_id","pin"],"v":[{"t":1,"s":"CLI-FIX0001"},{"t":1,"s":"123456"}]},"o":0},{"t":10,"i":2,"p":{"k":[],"v":[]},"o":0}]},"o":0},"f":127,"m":[]}'

export const session = { customer_id: 'CLI-FIX0001', session_ref: 'ref-1', segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }

type Hold = { match: (req: IncomingMessage) => boolean; onReach: () => void; released: Promise<{ status: number; body: unknown }> }
export type Held = { reached: Promise<void>; release: (status?: number, body?: unknown) => void }
/** What the fake API does with a DELETE of a session: `drop` closes the connection, `hang` never answers. */
export type DeleteMode = 'ok' | 'error' | 'hang' | 'drop'

export async function startCustomerApp(fake: FakeApi) {
  const seen: { url: string; method: string; token: string | undefined }[] = []
  // The sessions the fake API considers alive, the tokens the next logins get (TOKEN once these run out), and what a DELETE does.
  const live = new Set([TOKEN])
  const nextTokens: string[] = []
  let deleteMode: DeleteMode = 'ok'
  const holds: Hold[] = []
  // A raw answer in place of the API's own, whatever it says: a 200 whose body is not JSON, for instance.
  let raw: { match: (req: IncomingMessage) => boolean; status: number; text: string } | null = null
  const api: Server = createServer(async (req, res) => {
    const reply = (status: number, body: unknown) => {
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(body))
    }
    const token = req.headers['x-session-token'] as string | undefined
    seen.push({ url: req.url ?? '', method: req.method ?? '', token })
    const held = holds.findIndex((h) => h.match(req))
    if (held >= 0) {
      const [gate] = holds.splice(held, 1)
      gate.onReach()
      const answer = await within(gate.released, 'a held request was never released by the test').catch(() => ({ status: 599, body: { detail: 'never released' } }))
      return reply(answer.status, answer.body)
    }
    if (raw?.match(req)) {
      res.writeHead(raw.status, { 'Content-Type': 'application/json' })
      return res.end(raw.text)
    }
    const alive = token !== undefined && live.has(token)
    if (req.url === '/auth/session' && req.method === 'POST') {
      const issued = nextTokens.shift() ?? TOKEN
      live.add(issued)
      return reply(200, { token: issued, expires_in: 900 })
    }
    if (req.url === '/auth/session' && req.method === 'DELETE') {
      if (deleteMode === 'drop') return req.socket.destroy()
      if (deleteMode === 'hang') return
      if (deleteMode === 'error') return reply(500, { detail: 'internal error' })
      if (token) live.delete(token)
      return reply(200, { ok: true })
    }
    if (req.url === '/auth/session') return alive ? reply(200, session) : reply(401, { detail: 'invalid or expired session' })
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
  const signIn = async (base = ORIGIN, proof: Record<string, string> = { Origin: base, 'Sec-Fetch-Site': 'same-origin' }, extra: Record<string, string> = {}) => {
    const assets = join(import.meta.dirname, '../../dist/server/assets')
    const file = readdirSync(assets).find((f) => f.startsWith('auth.functions-') && readFileSync(join(assets, f), 'utf8').includes('name: "login"'))
    const id = /id: "([0-9a-f]+)",\s*name: "login"/.exec(readFileSync(join(assets, file ?? ''), 'utf8'))?.[1]
    assert.ok(id, 'the login server function is in the build')
    return built.default.fetch(
      new Request(`${base}/_serverFn/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-tsr-serverFn': 'true', Accept: 'application/json', ...proof, ...extra },
        body: SIGN_IN_BODY,
      }),
    )
  }
  const fetch = (request: Request) => built.default.fetch(request)
  const rpc = (name: string, init?: RpcInit) => fetch(rpcRequest(ORIGIN, name, init))
  // Holds the next request the API gets that `match` says yes to, until the test releases it with an answer: a slow response that
  // arrives after other things have happened.
  const hold = (match: (req: IncomingMessage) => boolean): Held => {
    let release!: (status?: number, body?: unknown) => void
    let reached!: () => void
    const released = new Promise<{ status: number; body: unknown }>((done) => (release = (status = 200, body: unknown = { detail: 'held response' }) => done({ status, body })))
    const arrived = new Promise<void>((done) => (reached = done))
    holds.push({ match, onReach: reached, released })
    return { reached: within(arrived, 'the API never got the request the test is holding'), release }
  }
  return {
    get, fetch, rpc, signIn, seen, hold,
    nextTokens: (...tokens: string[]) => void nextTokens.push(...tokens),
    answerRaw: (match: (req: IncomingMessage) => boolean, status: number, text: string) => void (raw = { match, status, text }),
    answerNormally: () => void (raw = null),
    isLive: (token: string) => live.has(token),
    setDelete: (mode: DeleteMode) => void (deleteMode = mode),
    close: () => {
      api.closeAllConnections()
      api.close()
    },
  }
}
