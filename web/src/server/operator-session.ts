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

/**
 * A login always gets a new id, and the session this browser held before it is consumed in the same step. If a second
 * login arrives with a cookie that was just consumed, it gets nothing (false) and its response must not touch the session
 * cookie: the winner's Set-Cookie may already be in the browser, and a deletion arriving after it would orphan that session.
 */
export function startOperatorSession(adminKey: string, operatorKey?: string, operator?: string): boolean {
  if (store.take(getCookie(name)) === 'already') return false
  setCookie(name, store.start(adminKey, operatorKey, operator), { ...options, maxAge: ABSOLUTE_MS / 1000 })
  return true
}

/** `touch: false` for the console's automatic refresh: it must not count as the operator being there. */
export function operatorSessionState(touch: boolean): SessionState {
  const id = getCookie(name)
  if (!id) return { status: 'anonymous' }
  const found = store.lookup(id, touch)
  if (found.status === 'active') return found
  // The session behind this id is gone (idle, over the cap, replaced, or the server restarted). The cookie is left alone:
  // responses cross on the wire, and a deletion arriving after the Set-Cookie of a newer login would erase that session
  // from the browser and orphan it on the server. It is cleared only by an explicit logout, or overwritten by a login.
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

/** The id in the request's cookie (what identifies the session this request used), or undefined. */
export const operatorSessionId = () => getCookie(name)

/**
 * Ends a session on the server, by id, and sends nothing to the browser. What an API error does to a session: the id
 * named is the one THIS request used, so if a login has replaced it meanwhile there is nothing left to end, and the
 * new session (under another id) is untouched. Only an explicit logout clears the cookie.
 */
export const invalidateOperatorSession = (id: string | undefined) => store.end(id)

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
