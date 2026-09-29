// Production server for the TanStack Start build: static files from dist/client and everything else through the app's fetch
// handler (dist/server/server.js). Node's built-ins only, so the image needs no extra package. `pnpm build` first.
//
//   PORT (3000), HOST (0.0.0.0)
//   AGENT_API_URL: where the Python API is (read per request by src/server/agent-api.ts)
//   TRUSTED_CLIENT_IP_HEADER: a header a proxy in front sets with the real client address and no client can forge
//     (CF-Connecting-IP on Render). Unset, this server writes the connection's own address into `x-peer-address` (dropping
//     any value the client sent) and points the app at it, so the API's per-client limits see one address per user.
//
// GET /_healthz answers 200 while this process is up, whatever the API is doing; /api/agent/health is the one that asks it.
import { createServer } from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { Readable } from 'node:stream'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = fileURLToPath(new URL('.', import.meta.url))
const clientDir = resolve(root, 'dist/client')
const port = Number(process.env.PORT || 3000)
const host = process.env.HOST || '0.0.0.0'
const PEER_HEADER = 'x-peer-address'
if (!process.env.TRUSTED_CLIENT_IP_HEADER) process.env.TRUSTED_CLIENT_IP_HEADER = PEER_HEADER

const { default: app } = await import(pathToFileURL(resolve(root, 'dist/server/server.js')).href)

const TYPES = {
  '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json',
}
const SECURITY = { 'x-content-type-options': 'nosniff', 'x-frame-options': 'DENY', 'referrer-policy': 'no-referrer' }

function staticFile(pathname) {
  if (pathname === '/' || pathname.includes('\0')) return null
  const file = resolve(clientDir, '.' + sep + normalize(decodeURIComponent(pathname)))
  if (!file.startsWith(clientDir + sep) || !existsSync(file) || !statSync(file).isFile()) return null
  return file
}

function toRequest(req) {
  const headers = new Headers()
  for (const [name, value] of Object.entries(req.headers)) {
    if (value === undefined) continue
    for (const v of Array.isArray(value) ? value : [value]) headers.append(name, v)
  }
  if (process.env.TRUSTED_CLIENT_IP_HEADER === PEER_HEADER) headers.set(PEER_HEADER, req.socket.remoteAddress ?? '')
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`)
  const body = req.method === 'GET' || req.method === 'HEAD' ? undefined : Readable.toWeb(req)
  return new Request(url, { method: req.method, headers, body, duplex: 'half' })
}

async function send(res, response) {
  const headers = {}
  for (const [name, value] of response.headers) if (name !== 'set-cookie') headers[name] = value
  const cookies = response.headers.getSetCookie()
  if (cookies.length) headers['set-cookie'] = cookies
  res.writeHead(response.status, { ...SECURITY, ...headers })
  if (!response.body) return res.end()
  Readable.fromWeb(response.body).on('error', () => res.destroy()).pipe(res)
}

const server = createServer(async (req, res) => {
  try {
    const { pathname } = new URL(req.url, 'http://localhost')
    if (pathname === '/_healthz') {
      res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' })
      return res.end('{"status":"alive"}')
    }
    const file = req.method === 'GET' || req.method === 'HEAD' ? staticFile(pathname) : null
    if (file) {
      res.writeHead(200, {
        ...SECURITY, 'content-type': TYPES[extname(file)] ?? 'application/octet-stream',
        'cache-control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'public, max-age=300',
      })
      return req.method === 'HEAD' ? res.end() : createReadStream(file).pipe(res)
    }
    await send(res, await app.fetch(toRequest(req)))
  } catch (error) {
    console.error(error)
    if (!res.headersSent) res.writeHead(500, { 'content-type': 'text/plain' })
    res.end('Internal Server Error')
  }
})

server.listen(port, host, () => console.log(`web listening on http://${host}:${port}`))
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => process.exit(0)))
