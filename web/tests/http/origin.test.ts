import assert from 'node:assert/strict'
import { after, before, beforeEach, describe, test } from 'node:test'
import { ADMIN, alertOf, assertRefused, ORIGIN, sessionCookie, startConsole } from './harness.ts'

let app: Awaited<ReturnType<typeof startConsole>>
before(async () => { app = await startConsole() })
after(() => app.close())

const PUBLIC = 'https://console.bank.example'
beforeEach(() => { process.env.WEB_PUBLIC_ORIGIN = PUBLIC })

// The request itself arrives at the public https URL, as it would behind a proxy that terminates TLS and keeps the Host.
const login = (headers: Record<string, string>, base = PUBLIC) => app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers, base })

describe('the origin the forms trust is the configured public one, scheme, host and port', () => {
  test('the exact public origin is accepted, however the browser proves it', async () => {
    const proofs: Record<string, string>[] = [
      { Origin: PUBLIC },
      { Origin: `${PUBLIC}/`, 'Sec-Fetch-Site': 'same-origin' },
      { Referer: `${PUBLIC}/operador/login` },
      { 'Sec-Fetch-Site': 'same-origin' },
    ]
    for (const headers of proofs) {
      const res = await login(headers)
      assert.equal(res.status, 303, JSON.stringify(headers))
      assert.ok(sessionCookie(res), JSON.stringify(headers))
    }
  })

  test('an http page on the same host cannot log a victim into an https console', async () => {
    const attacks: Record<string, string>[] = [
      { Origin: 'http://console.bank.example' },
      { Referer: 'http://console.bank.example/operador/login' },
      { Origin: 'http://console.bank.example', 'Sec-Fetch-Site': 'same-origin' },
    ]
    for (const headers of attacks) {
      const res = await login(headers)
      assertRefused(res, 'origen', JSON.stringify(headers))
    }
  })

  test('another port or a look-alike host is another origin', async () => {
    const others: Record<string, string>[] = [
      { Origin: 'https://console.bank.example:8443' },
      { Referer: 'https://console.bank.example:8443/x' },
      { Origin: 'https://console.bank.example.attacker.invalid' },
      { Origin: 'https://attacker.invalid' },
    ]
    for (const headers of others) {
      assertRefused(await login(headers), 'origen', JSON.stringify(headers))
    }
  })

  test('proxy headers do not make an origin ours', async () => {
    const res = await login({ Origin: 'http://console.bank.example', 'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'console.bank.example', Forwarded: 'proto=https;host=console.bank.example' })
    assertRefused(res, 'origen')
  })

  test('the request URL and Host header do not decide it either when a public origin is configured', async () => {
    const res = await login({ Origin: ORIGIN, 'Sec-Fetch-Site': 'same-origin' }, ORIGIN)
    assertRefused(res, 'origen', 'http://console.test is not the configured origin')
  })
})

describe('a list of origins: the local stack answers on 127.0.0.1 and on localhost', () => {
  const LOCAL = ['http://127.0.0.1:3000', 'http://localhost:3000']
  beforeEach(() => { process.env.WEB_PUBLIC_ORIGIN = LOCAL.join(',') })

  for (const origin of LOCAL) {
    test(`${origin} is accepted, and its session cookie opens the console`, async () => {
      const res = await login({ Origin: origin, Referer: `${origin}/operador/login`, 'Sec-Fetch-Site': 'same-origin' }, origin)
      assert.equal(res.status, 303)
      assert.equal(res.headers.get('location'), '/operador/ingreso?to=%2Foperador%2Fcola')
      const cookie = sessionCookie(res)
      assert.ok(cookie)
      assert.equal((await app.send('/operador/cola', { headers: { Cookie: cookie }, base: origin })).status, 200)
    })
  }

  test('another host, another port or another scheme is refused', async () => {
    for (const foreign of ['http://localhost:3001', 'http://127.0.0.1:8000', 'https://localhost:3000', 'http://192.168.1.20:3000', 'https://attacker.invalid']) {
      const res = await login({ Origin: foreign, Referer: `${foreign}/x`, 'Sec-Fetch-Site': 'cross-site' }, LOCAL[0])
      assertRefused(res, 'origen', foreign)
    }
  })

  test('proxy headers still do not add an origin to the list', async () => {
    const res = await login({ Origin: 'http://console.bank.example', 'X-Forwarded-Host': 'localhost:3000', 'X-Forwarded-Proto': 'http' }, LOCAL[0])
    assertRefused(res, 'origen')
  })

  test('a wildcard is not an origin: the whole value is refused', async () => {
    process.env.WEB_PUBLIC_ORIGIN = `${LOCAL[0]},*`
    const res = await login({ Origin: LOCAL[0], 'Sec-Fetch-Site': 'same-origin' }, LOCAL[0])
    assertRefused(res, 'origen-config')
  })
})

describe('a refused post explains itself on the login page instead of leaving a blank 403', () => {
  // The notice rides in the URL, so a browser that keeps no cookie (WebKit with a Secure one over plain http) still sees it: every
  // request below goes out with no cookie at all.
  const follow = async (refused: Response, base: string, headers: Record<string, string> = {}) =>
    (await app.send(refused.headers.get('location')!, { headers, base })).text()

  test('the notice names the configured origins, in Spanish and in Portuguese', async () => {
    process.env.WEB_PUBLIC_ORIGIN = 'http://127.0.0.1:3000,http://localhost:3000'
    const base = 'http://127.0.0.1:3000'
    for (const path of ['/operador/sesion', '/operador/clave', '/operador/salir']) {
      const refused = await app.send(path, { method: 'POST', fields: { admin_key: ADMIN, operator_key: 'k' }, headers: { Origin: 'http://192.168.1.20:3000' }, base })
      assertRefused(refused, 'origen', path)
      assert.match(alertOf(await follow(refused, base)) ?? '', /^No pudimos verificar el origen del formulario\. Ingresar desde http:\/\/127\.0\.0\.1:3000, http:\/\/localhost:3000\./, path)
      assert.match(alertOf(await follow(refused, base, { Cookie: 'cecilai_lang=pt' })) ?? '', /^Não conseguimos verificar a origem do formulário\. Entrar por http:\/\/127\.0\.0\.1:3000, http:\/\/localhost:3000\./, path)
    }
  })

  test('the notice never echoes what the request carried: not the keys, not the origin it sent', async () => {
    process.env.WEB_PUBLIC_ORIGIN = PUBLIC
    const res = await app.send('/operador/sesion', { fields: { admin_key: ADMIN, redirect: '/x' }, headers: { Origin: 'https://attacker.invalid/<script>' }, base: PUBLIC })
    assertRefused(res, 'origen')
    const page = await follow(res, PUBLIC)
    assert.ok(!page.includes(ADMIN) && !page.includes('attacker.invalid'))
    assert.match(alertOf(page) ?? '', /Ingresar desde https:\/\/console\.bank\.example\./)
  })

  test('the reason is a closed list: anything else in the URL shows nothing, and is not echoed', async () => {
    process.env.WEB_PUBLIC_ORIGIN = PUBLIC
    for (const motivo of ['<script>alert(1)</script>', 'origen%00', 'ORIGEN', 'admin_key=' + ADMIN]) {
      const page = await (await app.send(`/operador/login?motivo=${encodeURIComponent(motivo)}`, { base: PUBLIC })).text()
      assert.equal(alertOf(page), null, motivo)
      assert.ok(!page.includes(ADMIN) && !page.includes('<script>alert'), motivo)
    }
  })

  test('with no usable origin configured the notice says so', async () => {
    process.env.WEB_PUBLIC_ORIGIN = 'not-an-origin-flash-test'
    const original = console.error
    console.error = () => {}
    try {
      const res = await login({ Origin: PUBLIC, 'Sec-Fetch-Site': 'same-origin' })
      assertRefused(res, 'origen-config')
      assert.match(alertOf(await follow(res, PUBLIC)) ?? '', /no tiene configurado su origen público \(WEB_PUBLIC_ORIGIN\)/)
    } finally { console.error = original }
  })

  test('a refusal sets no cookie, not even one the browser could drop: it is the same for a browser that keeps none', async () => {
    process.env.WEB_PUBLIC_ORIGIN = 'https://console.bank.example'
    const res = await app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: { Origin: 'http://console.bank.example' }, base: PUBLIC })
    assert.deepEqual(res.headers.getSetCookie(), [])
  })
})

describe('a list is valid only if every entry is a pure origin: one bad entry refuses everything', () => {
  const original = console.error
  beforeEach(() => { console.error = () => {} })
  after(() => { console.error = original })

  const cases: [string, string, string][] = [
    ['a wildcard next to a real origin', 'https://console.bank.example,https://*.bank.example', 'https://console.bank.example'],
    ['userinfo that would make the host attacker.invalid', 'https://trusted.example@attacker.invalid', 'https://attacker.invalid'],
    ['a path', 'https://console.bank.example/operador', 'https://console.bank.example'],
    ['a query', 'https://console.bank.example?x=1', 'https://console.bank.example'],
    ['a fragment', 'https://console.bank.example#x', 'https://console.bank.example'],
  ]
  for (const [name, value, logged] of cases) {
    test(`${name}: ${value}`, async () => {
      process.env.WEB_PUBLIC_ORIGIN = value
      const res = await login({ Origin: logged, 'Sec-Fetch-Site': 'same-origin' }, logged)
      assertRefused(res, 'origen-config')
    })
  }
})

describe('in production the public origin is required', () => {
  const errors: string[] = []
  const original = console.error
  beforeEach(() => { errors.length = 0; console.error = (...args: unknown[]) => void errors.push(args.join(' ')) })
  after(() => { console.error = original })

  for (const [name, value] of [['missing', undefined], ['empty', ''], ['not a URL', 'console.bank.example'], ['not http(s)', 'ftp://console.bank.example']] as const) {
    test(`${name}: every form post is refused with a clear log line`, async () => {
      if (value === undefined) delete process.env.WEB_PUBLIC_ORIGIN
      else process.env.WEB_PUBLIC_ORIGIN = value
      const res = await login({ Origin: PUBLIC, 'Sec-Fetch-Site': 'same-origin' })
      assertRefused(res, 'origen-config')
      assert.ok(errors.some((line) => line.includes('WEB_PUBLIC_ORIGIN')), `logged: ${errors.join(' | ')}`)
    })
  }
})

describe('a refusal is shown even when the operator already has a session', () => {
  const HOME = 'http://127.0.0.1:3000'
  beforeEach(() => { process.env.WEB_PUBLIC_ORIGIN = `${HOME},http://localhost:3000` })

  for (const path of ['/operador/clave', '/operador/salir']) {
    test(`${path}: the whole chain, post -> login page, keeps the session and says why`, async () => {
      const cookie = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: { Origin: HOME }, base: HOME }))!
      const refused = await app.send(path, { method: 'POST', fields: { operator_key: 'k' }, headers: { Origin: 'http://192.168.1.20:3000', Cookie: cookie }, base: HOME })
      assertRefused(refused, 'origen', path)
      // The login page of a signed-in operator used to bounce to the queue, swallowing the notice
      const es = await app.send(refused.headers.get('location')!, { headers: { Cookie: cookie }, base: HOME })
      assert.equal(es.status, 200, `${path} landed on ${es.headers.get('location')}`)
      assert.match(alertOf(await es.text()) ?? '', /^No pudimos verificar el origen del formulario\. Ingresar desde http:\/\/127\.0\.0\.1:3000, http:\/\/localhost:3000\./)
      const pt = await app.send(refused.headers.get('location')!, { headers: { Cookie: `${cookie}; cecilai_lang=pt` }, base: HOME })
      assert.match(alertOf(await pt.text()) ?? '', /^Não conseguimos verificar a origem do formulário\. Entrar por http:\/\/127\.0\.0\.1:3000, http:\/\/localhost:3000\./)
      assert.equal((await app.send('/operador/cola', { headers: { Cookie: cookie }, base: HOME })).status, 200, 'the refusal did not end the session')
    })
  }

  test('a signed-in operator who opens the login page for no reason still goes to the queue', async () => {
    const cookie = sessionCookie(await app.send('/operador/sesion', { fields: { admin_key: ADMIN }, headers: { Origin: HOME }, base: HOME }))!
    const res = await app.send('/operador/login', { headers: { Cookie: cookie }, base: HOME })
    assert.equal(res.status, 307)
    assert.equal(res.headers.get('location'), '/operador/cola')
  })
})
