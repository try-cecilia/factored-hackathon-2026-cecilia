import '@tanstack/react-start/server-only'
import { loginFromForm, operatorKeyFromForm, type KeyProbe } from './operator-login.ts'
import { probeAdminKey, probeOperatorKey } from './operator-api'
import { endOperatorSession, getOperatorSession, setFlash, startOperatorSession } from './operator-session'

// The operator forms are plain HTML posts that land here, so the keys never pass through the page's JavaScript:
// they are read from the form body, checked against the API, kept in the server-side session and answered with a
// redirect (post/redirect/get). Nothing in the response carries a key, only a Location and a flash code.
const admin: KeyProbe = (key) => probeAdminKey(key)
const operator: KeyProbe = (key) => probeOperatorKey(key)

const see = (to: string) => new Response(null, { status: 303, headers: { Location: to, 'Cache-Control': 'no-store' } })

const readForm = (request: Request) => request.formData().catch(() => null)

export async function handleLogin(request: Request) {
  const form = await readForm(request)
  if (!form) return see('/operador/login')
  const outcome = await loginFromForm(form, { admin, operator })
  if (!outcome.ok) {
    setFlash(outcome.flash)
    return see(outcome.to)
  }
  startOperatorSession(outcome.keys.adminKey, outcome.keys.operatorKey, outcome.keys.operator)
  return see(outcome.to)
}

export async function handleAddKey(request: Request) {
  const form = await readForm(request)
  const session = getOperatorSession(true)
  if (!form || !session) return see('/operador/login')
  const outcome = await operatorKeyFromForm(form, operator)
  if (!outcome.ok) {
    setFlash(outcome.flash)
    return see(outcome.to)
  }
  session.operatorKey = outcome.operatorKey
  session.operator = outcome.operator
  return see(outcome.to)
}

export async function handleLogout() {
  endOperatorSession()
  return see('/operador/login')
}
