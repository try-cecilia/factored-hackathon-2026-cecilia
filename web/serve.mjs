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
// The build's text files (JS, CSS...) go compressed when the browser asks for it (brotli or gzip, see `encodingFor`); the pages
// the app renders do not: they carry session data next to what a visitor can put in the URL (BREACH).
import { createServer } from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { pipeline, Readable } from 'node:stream'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { constants, createBrotliCompress, createGzip } from 'node:zlib'

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
// same-origin, not no-referrer: under no-referrer a browser sends `Origin: null` with a form post, and the operator forms'
// origin check (src/server/origin-check.ts) would refuse every login. Nothing is sent to other sites either way.
// A CSP without script-src: the pages hydrate with inline scripts, and pinning them needs a nonce per response, which this server
// cannot add without a browser to check it against. What it does say cannot break a page: nothing may frame it, change its base,
// embed an object, or receive a form from it at another origin.
const CSP = "frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"
// HSTS only when every public origin is https: a browser ignores it over http, and a local run on http must stay reachable.
const publicOrigins = (process.env.WEB_PUBLIC_ORIGIN ?? '').split(',').map((o) => o.trim()).filter(Boolean)
const HSTS = publicOrigins.length > 0 && publicOrigins.every((o) => o.startsWith('https://')) ? { 'strict-transport-security': 'max-age=15724800; includeSubDomains' } : {}
const SECURITY = { 'x-content-type-options': 'nosniff', 'x-frame-options': 'DENY', 'referrer-policy': 'same-origin', 'content-security-policy': CSP, ...HSTS }

// Images and fonts are compressed already.
const COMPRESSIBLE = new Set(['.js', '.mjs', '.css', '.html', '.json', '.svg', '.txt', '.map'])

/**
 * The coding to send, from Accept-Encoding (RFC 9110, 12.5.3): the highest weight wins, and between equal weights br, then gzip,
 * then the file as it is. `*` stands for the codings not named; identity is acceptable unless refused by name or by `*;q=0`, and
 * below any coding the browser asked for. Without the header, the file as it is. null: nothing offered is acceptable (406).
 */
function encodingFor(header, offered) {
  if (header === undefined) return 'identity'
  const weights = new Map()
  for (const part of String(header).toLowerCase().split(',')) {
    const [name, ...params] = part.split(';').map((p) => p.trim())
    if (!name) continue
    const q = params.find((p) => p.startsWith('q='))
    const weight = q ? Number(q.slice(2)) : 1
    weights.set(name, Number.isFinite(weight) ? weight : 0)
  }
  const weightOf = (coding) => weights.get(coding) ?? weights.get('*') ?? (coding === 'identity' ? 0.001 : 0)
  let best = null
  for (const coding of offered) if (weightOf(coding) > 0 && (best === null || weightOf(coding) > weightOf(best))) best = coding
  return best
}

// Compressed while it is sent, never buffered whole. Brotli at quality 5: most of its gain over gzip for a fraction of the CPU of
// its top setting, which a request cannot afford.
const compressor = {
  br: () => createBrotliCompress({ params: { [constants.BROTLI_PARAM_QUALITY]: 5, [constants.BROTLI_PARAM_MODE]: constants.BROTLI_MODE_TEXT } }),
  gzip: () => createGzip(),
}

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
      res.writeHead(200, { ...SECURITY, 'content-type': 'application/json', 'cache-control': 'no-store' })
      return res.end('{"status":"alive"}')
    }
    const file = req.method === 'GET' || req.method === 'HEAD' ? staticFile(pathname) : null
    if (file) {
      const compressible = COMPRESSIBLE.has(extname(file))
      const chosen = encodingFor(req.headers['accept-encoding'], compressible ? ['br', 'gzip', 'identity'] : ['identity'])
      if (chosen === null) {
        res.writeHead(406, { ...SECURITY, 'content-type': 'text/plain; charset=utf-8', vary: 'accept-encoding' })
        return res.end('Not Acceptable')
      }
      const encoding = chosen === 'identity' ? null : chosen
      res.writeHead(200, {
        ...SECURITY, 'content-type': TYPES[extname(file)] ?? 'application/octet-stream',
        'cache-control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'public, max-age=300',
        // A cache in between keeps one copy per encoding.
        ...(compressible && { vary: 'accept-encoding' }),
        ...(encoding && { 'content-encoding': encoding }),
      })
      if (req.method === 'HEAD') return res.end()
      if (!encoding) return createReadStream(file).pipe(res)
      return pipeline(createReadStream(file), compressor[encoding](), res, () => {})
    }
    await send(res, await app.fetch(toRequest(req)))
  } catch (error) {
    console.error(error)
    if (!res.headersSent) res.writeHead(500, { ...SECURITY, 'content-type': 'text/plain' })
    res.end('Internal Server Error')
  }
})

server.listen(port, host, () => console.log(`web listening on http://${host}:${port}`))
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => process.exit(0)))
