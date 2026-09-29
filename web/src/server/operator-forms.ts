import '@tanstack/react-start/server-only'
import { checkOrigin, originConfigFromEnv } from './origin-check.ts'
import { DEFAULT_LANDING, loginFromForm, operatorKeyFromForm, type KeyProbe } from './operator-login.ts'
import { sameOriginPath } from './safe-path.ts'
import { probeAdminKey, probeOperatorKey } from './operator-api'
import { elevateOperatorSession, endOperatorSession, operatorSessionState, setFlash, startOperatorSession } from './operator-session'

// The operator forms are plain HTML posts that land here, so the keys never pass through the page's JavaScript:
// they are read from the form body, checked against the API, kept in the server-side session and answered with a
// redirect (post/redirect/get). Nothing in the response carries a key, only a Location and a flash code.
const admin: KeyProbe = (key) => probeAdminKey(key)
const operator: KeyProbe = (key) => probeOperatorKey(key)

const see = (to: string) => new Response(null, { status: 303, headers: { Location: to, 'Cache-Control': 'no-store' } })

const readForm = (request: Request) => request.formData().catch(() => null)

// A post that does not prove it came from one of our pages is refused before it reads a body or touches the session. The
// answer is not a bare 403 page (a person who opened the console at another address than the configured one would see only
// "Forbidden"): it is a redirect to the login whose `motivo` says why, one of a closed list and never anything from the request.
// It travels in the URL, not in a cookie: a browser that refuses cookies (Safari with a Secure one over plain http, the very
// mistake this notice is about) would never show it.
const refused = (motivo: 'origen' | 'origen-config') => see(`/operador/login?motivo=${motivo}`)

// One log line per minute per bad value, so a flood of hostile posts does not flood the log.
const loggedAt = new Map<string, number>()
function foreign(request: Request) {
  const config = originConfigFromEnv()
  const verdict = checkOrigin(request, config)
  if (verdict.ok) return null
  const key = String(config.publicOrigin)
  if (verdict.reason === 'misconfigured' && Date.now() - (loggedAt.get(key) ?? 0) > 60_000) {
    loggedAt.set(key, Date.now())
    console.error(
      '[operator] refusing form posts: WEB_PUBLIC_ORIGIN must be the public origin of the console (for example https://console.bank.example) ' +
        'in production, and an http(s) origin wherever it is set.',
    )
  }
  return refused(verdict.reason === 'misconfigured' ? 'origen-config' : 'origen')
}

export async function handleLogin(request: Request) {
  const denied = foreign(request)
  if (denied) return denied
  const form = await readForm(request)
  if (!form) return see('/operador/login')
  const outcome = await loginFromForm(form, { admin, operator })
  if (!outcome.ok) {
    setFlash(outcome.flash)
    return see(outcome.to)
  }
  if (!startOperatorSession(outcome.keys.adminKey, outcome.keys.operatorKey, outcome.keys.operator)) {
    setFlash('session_replaced')
    return see('/operador/login')
  }
  return see(arrival(outcome.to))
}

// Where a login lands first. The Set-Cookie of the login can come back unusable (a browser that refuses the cookie, such as
// Safari with a Secure one over plain http) and the server cannot know when it sends it. So the login redirects here, to a
// GET that carries the cookie the browser did keep: with a session it goes on to where the operator wanted, without one it
// says why the login did not take, instead of leaving a login form that looks like nothing happened.
const arrival = (to: string) => `/operador/ingreso?to=${encodeURIComponent(to)}`

export function handleArrival(request: Request) {
  const to = sameOriginPath(new URL(request.url).searchParams.get('to')) ?? DEFAULT_LANDING
  if (operatorSessionState(false).status === 'active') return see(to)
  return see(`/operador/login?redirect=${encodeURIComponent(to)}&motivo=sin-cookie`)
}

export async function handleAddKey(request: Request) {
  const denied = foreign(request)
  if (denied) return denied
  const form = await readForm(request)
  // Without a live session there is nothing to raise, and the API is not asked to check keys for a stranger.
  if (!form || operatorSessionState(true).status !== 'active') return see('/operador/login')
  const outcome = await operatorKeyFromForm(form, operator)
  if (!outcome.ok) {
    setFlash(outcome.flash)
    return see(outcome.to)
  }
  if (!elevateOperatorSession(outcome.operatorKey, outcome.operator)) return see('/operador/login')
  return see(outcome.to)
}

export async function handleLogout(request: Request) {
  const denied = foreign(request)
  if (denied) return denied
  endOperatorSession()
  return see('/operador/login')
}
