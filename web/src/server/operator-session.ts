import '@tanstack/react-start/server-only'
import { deleteCookie, getCookie, setCookie } from '@tanstack/react-start/server'
import { ABSOLUTE_MS, IDLE_MS, SessionStore, type OperatorSession } from './operator-store.ts'

// The operator's keys never reach the browser: not in JS, not in a cookie. The browser holds an opaque id in an
// httpOnly cookie and this process holds the keys in memory. Tradeoff: a restart (or a second instance) signs
// everyone out, which is acceptable for a console with a handful of operators; docs/integracion.md has the rest.
// On globalThis so a dev reload of this module does not drop the sessions in memory.
const holder = globalThis as { __cecilaiOperatorStore?: SessionStore }
// OPERATOR_IDLE_SECONDS shortens the idle window (default 1800, at least 10) to try the expiry without waiting half an hour.
const idleSeconds = Number(process.env.OPERATOR_IDLE_SECONDS)
const store = (holder.__cecilaiOperatorStore ??= new SessionStore(Date.now, idleSeconds >= 10 ? idleSeconds * 1000 : IDLE_MS))

const secure = process.env.NODE_ENV === 'production'
const name = secure ? '__Host-cecilai_operator' : 'cecilai_operator'
const options = { httpOnly: true, secure, sameSite: 'strict', path: '/' } as const

export type { OperatorSession }
export type SessionState = { status: 'active'; session: OperatorSession } | { status: 'expired' } | { status: 'anonymous' }

/** A login always gets a new id, and whatever session this browser held before it is ended. */
export function startOperatorSession(adminKey: string, operatorKey?: string, operator?: string) {
  store.end(getCookie(name))
  setCookie(name, store.start(adminKey, operatorKey, operator), { ...options, maxAge: ABSOLUTE_MS / 1000 })
}

/** `touch: false` for the console's automatic refresh: it must not count as the operator being there. */
export function operatorSessionState(touch: boolean): SessionState {
  const id = getCookie(name)
  if (!id) return { status: 'anonymous' }
  const found = store.lookup(id, touch)
  if (found.status === 'active') return found
  deleteCookie(name, options) // a cookie for a session that is gone (idle, over the cap, or the server restarted)
  return { status: 'expired' }
}

export function getOperatorSession(touch: boolean): OperatorSession | null {
  const state = operatorSessionState(touch)
  return state.status === 'active' ? state.session : null
}

/** Adds the operator key under a new id and a new cookie; the read-only cookie the browser held stops working. */
export function elevateOperatorSession(operatorKey: string, operator?: string) {
  const id = store.elevate(getCookie(name), operatorKey, operator)
  if (id) setCookie(name, id, { ...options, maxAge: ABSOLUTE_MS / 1000 })
  return id !== null
}

export function endOperatorSession() {
  store.end(getCookie(name))
  deleteCookie(name, options)
}

// A one-shot message for the page a form post redirects to ("that key is not valid"). It is a fixed code such as
// `operator_401`, never anything the operator typed.
const flashName = secure ? '__Host-cecilai_operator_flash' : 'cecilai_operator_flash'
const flashOptions = { httpOnly: true, secure, sameSite: 'strict', path: '/', maxAge: 60 } as const

export const setFlash = (code: string) => setCookie(flashName, code, flashOptions)

export function takeFlash() {
  const code = getCookie(flashName)
  if (code) deleteCookie(flashName, flashOptions)
  return code && /^[a-z]+_[a-z0-9]+$/.test(code) ? code : null
}
