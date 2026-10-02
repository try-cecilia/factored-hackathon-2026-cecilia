// A server function called the way the browser calls it, against the production build: its id is read from the build, and its
// payload is written by the framework's own serializer (seroval), so a test needs no hand-written wire format.
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fromCrossJSON, toJSON, type SerovalNode } from 'seroval'

const assets = join(import.meta.dirname, '../../dist/server/assets')

export function serverFnId(name: string) {
  for (const file of readdirSync(assets).filter((f) => f.endsWith('.js'))) {
    const id = new RegExp(`id: "([0-9a-f]+)",\\s*name: "${name}"`).exec(readFileSync(join(assets, file), 'utf8'))?.[1]
    if (id) return id
  }
  assert.fail(`the server function ${name} is not in the build`)
}

export type RpcInit = {
  /** GET for a read, POST for an action; the server function itself says which it accepts. */
  method?: 'GET' | 'POST'
  data?: unknown
  /** What the browser says about where the call came from; the default is a call from the app's own page. */
  proof?: Record<string, string>
  headers?: Record<string, string>
}

export function rpcRequest(base: string, name: string, { method = 'POST', data, proof, headers }: RpcInit = {}) {
  const sent = new Headers({ 'x-tsr-serverFn': 'true', Accept: 'application/json', ...(proof ?? { Origin: base, 'Sec-Fetch-Site': 'same-origin' }), ...headers })
  const payload = JSON.stringify(toJSON({ data, context: {} }))
  const url = `${base}/_serverFn/${serverFnId(name)}`
  if (method === 'GET') return new Request(data === undefined ? url : `${url}?payload=${encodeURIComponent(payload)}`, { headers: sent })
  sent.set('Content-Type', 'application/json')
  return new Request(url, { method, headers: sent, body: payload })
}

/**
 * What a server function answered, as the browser's client would read it: `result` for a return value, `error` for the message of
 * an Error it threw (the framework puts an Error's message on the wire, and only that), and the whole `text` for a test that
 * wants to prove something is not in the answer anywhere.
 */
export async function rpcOutcome(response: Response) {
  const text = await response.text()
  const [result, error] = (JSON.parse(text) as { p: { v: SerovalNode[] } }).p.v
  return {
    status: response.status,
    text,
    result: fromCrossJSON(result, { plugins: [] }) as unknown,
    error: error.t === 25 ? String(fromCrossJSON((error as unknown as { s: { message: SerovalNode } }).s.message, { plugins: [] })) : undefined,
  }
}
