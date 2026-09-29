import '@tanstack/react-start/server-only'
import { checkOrigin, originConfigFromEnv } from './origin-check.ts'
import { loginFromForm, operatorKeyFromForm, type KeyProbe } from './operator-login.ts'
import { probeAdminKey, probeOperatorKey } from './operator-api'
import { elevateOperatorSession, endOperatorSession, operatorSessionState, setFlash, startOperatorSession } from './operator-session'

// The operator forms are plain HTML posts that land here, so the keys never pass through the page's JavaScript:
// they are read from the form body, checked against the API, kept in the server-side session and answered with a
// redirect (post/redirect/get). Nothing in the response carries a key, only a Location and a flash code.
const admin: KeyProbe = (key) => probeAdminKey(key)
const operator: KeyProbe = (key) => probeOperatorKey(key)

const see = (to: string) => new Response(null, { status: 303, headers: { Location: to, 'Cache-Control': 'no-store' } })

const readForm = (request: Request) => request.formData().catch(() => null)

// A post that does not prove it came from one of our pages is refused before it reads a body or touches a cookie.
const refused = () => new Response('Forbidden', { status: 403, headers: { 'Cache-Control': 'no-store' } })

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
  return refused()
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
  return see(outcome.to)
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
