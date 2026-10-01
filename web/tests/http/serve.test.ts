// web/serve.mjs itself, the production server of the image: run as a process on a free port, in front of the build.
import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
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
async function raw(path: string, acceptEncoding?: string, method = 'GET', body?: Buffer | Buffer[]) {
  const { request } = await import('node:http')
  return new Promise<{ status: number; headers: Record<string, string | string[] | undefined>; body: Buffer }>((done, fail) => {
    // A Buffer goes with its Content-Length; an array of chunks goes chunked, with no length declared.
    const headers: Record<string, string> = acceptEncoding === undefined ? {} : { 'accept-encoding': acceptEncoding }
    if (body !== undefined) headers['content-type'] = 'application/x-www-form-urlencoded'
    const req = request(`${base}${path}`, { method, headers }, (res) => {
      const chunks: Buffer[] = []
      res.on('data', (c: Buffer) => chunks.push(c))
      res.on('end', () => done({ status: res.statusCode ?? 0, headers: res.headers, body: Buffer.concat(chunks) }))
    })
    req.on('error', fail)
    if (Array.isArray(body)) for (const chunk of body) req.write(chunk)
    req.end(Array.isArray(body) ? undefined : body)
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

  test('the weights decide: gzip at q=1 wins over brotli at q=0.1', async () => {
    const res = await raw(`/assets/${script}`, 'gzip;q=1, br;q=0.1')
    assert.equal(res.headers['content-encoding'], 'gzip')
    assert.ok(gunzipSync(res.body).equals(original))
    const star = await raw(`/assets/${script}`, 'br;q=0.2, *;q=0.5')
    assert.equal(star.headers['content-encoding'], 'gzip')
  })

  test('refusing every coding, identity included, is a 406, not the file as it is', async () => {
    for (const header of ['identity;q=0, gzip;q=0, br;q=0', '*;q=0']) {
      const res = await raw(`/assets/${script}`, header)
      assert.equal(res.status, 406, header)
      assert.equal(res.headers['content-encoding'], undefined)
      assert.match(String(res.headers.vary), /accept-encoding/i)
    }
    const identityOnly = await raw(`/assets/${script}`, 'identity;q=0.5, gzip;q=0, br;q=0')
    assert.equal(identityOnly.status, 200)
    assert.equal(identityOnly.headers['content-encoding'], undefined)
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

describe('security headers', () => {
  const csp = "frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"

  test('every kind of answer carries them: a static file, the health check, a page, a refused encoding', async () => {
    for (const [path, encoding] of [[`/assets/${script}`, undefined], ['/_healthz', undefined], ['/', undefined], [`/assets/${script}`, 'identity;q=0, *;q=0']] as const) {
      const { headers } = await raw(path, encoding)
      assert.equal(headers['content-security-policy'], csp, path)
      assert.equal(headers['x-content-type-options'], 'nosniff', path)
      assert.equal(headers['x-frame-options'], 'DENY', path)
      assert.equal(headers['referrer-policy'], 'same-origin', path)
    }
  })

  test('HSTS is not sent on this http run, and only an all-https public origin turns it on', async () => {
    assert.equal((await raw('/_healthz')).headers['strict-transport-security'], undefined)
    const hsts = async (origin: string) => {
      const port = await freePort()
      const child = spawn(process.execPath, ['serve.mjs'], { cwd: web, env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', AGENT_API_URL: 'http://127.0.0.1:9', WEB_PUBLIC_ORIGIN: origin }, stdio: 'ignore' })
      try {
        for (let i = 0; i < 100 && !(await fetch(`http://127.0.0.1:${port}/_healthz`).then((r) => r.ok, () => false)); i++) await new Promise((wait) => setTimeout(wait, 50))
        return (await fetch(`http://127.0.0.1:${port}/_healthz`)).headers.get('strict-transport-security')
      } finally {
        child.kill()
      }
    }
    assert.equal(await hsts('https://console.bank.example'), 'max-age=15724800; includeSubDomains')
    assert.equal(await hsts('https://a.example,http://127.0.0.1:3000'), null)
    // The parser the origin check uses decides, not a prefix: a value it refuses (a path, userinfo, a wildcard, a blank entry) sends none.
    for (const refused of ['https://console.bank.example/path', 'https://trusted.example@attacker.invalid', 'https://*.bank.example', 'https://a.example,', 'https://a.example, ,https://b.example']) {
      assert.equal(await hsts(refused), null, refused)
    }
    assert.equal(await hsts('https://a.example, https://B.example:8443/'), 'max-age=15724800; includeSubDomains')
  })
})

// What the one server in front of the app answers for itself: a hostile body, a method nobody uses, a path that is not a path.
describe('the server\'s own answers', () => {
  const KIB = 1024
  const form = (bytes: number) => Buffer.from('admin_key=' + 'x'.repeat(bytes - 'admin_key='.length))

  test('a POST body over 16 KiB is a 413 before the app sees it, declared by its length or sent in chunks', async () => {
    for (const path of ['/operador/sesion', '/login', '/_serverFn/anything']) {
      const declared = await raw(path, undefined, 'POST', form(20 * KIB))
      assert.equal(declared.status, 413, path)
      assert.equal(declared.headers['content-type'], 'text/plain; charset=utf-8')
      assert.equal(declared.headers['content-security-policy'], "frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'")
      const chunked = await raw(path, undefined, 'POST', [form(10 * KIB), form(10 * KIB)])
      assert.equal(chunked.status, 413, `${path} chunked`)
    }
  })

  test('a body at the limit still reaches the app: the cap is on size, not on posting', async () => {
    const res = await raw('/operador/sesion', undefined, 'POST', form(16 * KIB))
    assert.notEqual(res.status, 413)
    assert.notEqual(res.status, 500)
    const small = await raw('/operador/sesion', undefined, 'POST', form(40))
    assert.notEqual(small.status, 413)
  })

  test('the health check answers GET and HEAD only; any other method is a 405 that names them', async () => {
    assert.equal((await raw('/_healthz')).status, 200)
    const head = await raw('/_healthz', undefined, 'HEAD')
    assert.equal(head.status, 200)
    assert.equal(head.body.length, 0)
    for (const method of ['PATCH', 'POST', 'PUT', 'DELETE']) {
      const res = await raw('/_healthz', undefined, method)
      assert.equal(res.status, 405, method)
      assert.equal(res.headers.allow, 'GET, HEAD')
      assert.equal(res.headers['content-type'], 'text/plain; charset=utf-8')
    }
  })

  test('a path that is not valid percent-encoding fails with a 500 that says its charset', async () => {
    const res = await raw('/%E0%A4%A')
    assert.equal(res.status, 500)
    assert.equal(res.headers['content-type'], 'text/plain; charset=utf-8')
    assert.equal(res.body.toString(), 'Internal Server Error')
  })
})

describe('the web tier serves only the extensions it has a type for (V12.5.1)', () => {
  const probes = ['__probe.bak', '__probe.swp', '__probe.zip', '__probe.js.map.orig', '__probe']
  after(() => probes.forEach((name) => rmSync(join(web, 'dist/client', name), { force: true })))

  test('a stray editor, backup or archive file in dist/client is not served; a known type still is', async () => {
    for (const name of probes) writeFileSync(join(web, 'dist/client', name), 'secret')
    writeFileSync(join(web, 'dist/client/__probe.txt'), 'plain')
    try {
      for (const name of probes) {
        const res = await raw(`/${name}`)
        assert.notEqual(res.status, 200, name)
        assert.ok(!res.body.toString().includes('secret'), name)
      }
      const known = await raw('/__probe.txt')
      assert.equal(known.status, 200)
      assert.equal(known.headers['content-type'], 'text/plain; charset=utf-8')
    } finally {
      rmSync(join(web, 'dist/client/__probe.txt'), { force: true })
    }
  })
})
