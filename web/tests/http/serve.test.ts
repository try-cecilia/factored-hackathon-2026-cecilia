// web/serve.mjs itself, the production server of the image: run as a process on a free port, in front of the build.
import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { readdirSync, readFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { join } from 'node:path'
import { after, before, describe, test } from 'node:test'
import { brotliDecompressSync, gunzipSync } from 'node:zlib'

const web = join(import.meta.dirname, '../..')
const assets = readdirSync(join(web, 'dist/client/assets'))
const script = assets.find((f) => f.endsWith('.js')) as string
const font = assets.find((f) => f.endsWith('.woff2')) as string
const original = readFileSync(join(web, 'dist/client/assets', script))

let server: ChildProcess
let base = ''

const freePort = () =>
  new Promise<number>((done) => {
    const probe = createServer().listen(0, '127.0.0.1', () => {
      const { port } = probe.address() as { port: number }
      probe.close(() => done(port))
    })
  })

before(async () => {
  const port = await freePort()
  base = `http://127.0.0.1:${port}`
  server = spawn(process.execPath, ['serve.mjs'], { cwd: web, env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', AGENT_API_URL: 'http://127.0.0.1:9' }, stdio: 'ignore' })
  for (let i = 0; i < 100; i++) {
    if (await fetch(`${base}/_healthz`).then((r) => r.ok, () => false)) return
    await new Promise((wait) => setTimeout(wait, 50))
  }
  throw new Error('serve.mjs did not start')
})
after(() => server.kill())

// fetch() would decode the body and hide the header it came with: a raw request keeps both as sent.
async function raw(path: string, acceptEncoding?: string, method = 'GET') {
  const { request } = await import('node:http')
  return new Promise<{ headers: Record<string, string | string[] | undefined>; body: Buffer }>((done, fail) => {
    const req = request(`${base}${path}`, { method, headers: acceptEncoding === undefined ? {} : { 'accept-encoding': acceptEncoding } }, (res) => {
      const chunks: Buffer[] = []
      res.on('data', (c: Buffer) => chunks.push(c))
      res.on('end', () => done({ headers: res.headers, body: Buffer.concat(chunks) }))
    })
    req.on('error', fail)
    req.end()
  })
}

describe('serve.mjs compresses the build\'s text files when asked', () => {
  test('gzip, with Vary and the immutable cache of a hashed asset', async () => {
    const res = await raw(`/assets/${script}`, 'gzip, deflate')
    assert.equal(res.headers['content-encoding'], 'gzip')
    assert.match(String(res.headers.vary), /accept-encoding/i)
    assert.equal(res.headers['cache-control'], 'public, max-age=31536000, immutable')
    assert.ok(gunzipSync(res.body).equals(original))
    assert.ok(res.body.length < original.length)
  })

  test('brotli when the browser takes it, gzip when it refuses brotli', async () => {
    const br = await raw(`/assets/${script}`, 'gzip, deflate, br')
    assert.equal(br.headers['content-encoding'], 'br')
    assert.ok(brotliDecompressSync(br.body).equals(original))
    const refused = await raw(`/assets/${script}`, 'br;q=0, gzip')
    assert.equal(refused.headers['content-encoding'], 'gzip')
  })

  test('as it is when not asked, still saying that it varies; a HEAD sends the headers only', async () => {
    const plain = await raw(`/assets/${script}`)
    assert.equal(plain.headers['content-encoding'], undefined)
    assert.match(String(plain.headers.vary), /accept-encoding/i)
    assert.ok(plain.body.equals(original))
    const identity = await raw(`/assets/${script}`, 'identity')
    assert.equal(identity.headers['content-encoding'], undefined)
    const head = await raw(`/assets/${script}`, 'gzip', 'HEAD')
    assert.equal(head.headers['content-encoding'], 'gzip')
    assert.equal(head.body.length, 0)
  })

  test('fonts and images go as they are: they are compressed already', async () => {
    const res = await raw(`/assets/${font}`, 'gzip, br')
    assert.equal(res.headers['content-encoding'], undefined)
    assert.equal(res.headers.vary, undefined)
  })

  test('a page the app renders is never compressed (it carries session data next to what a URL can inject)', async () => {
    const res = await raw('/login', 'gzip, br')
    assert.equal(res.headers['content-encoding'], undefined)
  })
})
