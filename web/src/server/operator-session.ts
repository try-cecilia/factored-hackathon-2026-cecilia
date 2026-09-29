import '@tanstack/react-start/server-only'
import { randomBytes } from 'node:crypto'
import { deleteCookie, getCookie, setCookie } from '@tanstack/react-start/server'

// The operator's keys never reach the browser: not in JS, not in a cookie. The browser holds an opaque id in an
// httpOnly cookie and this process holds the keys in memory. Tradeoff: a restart (or a second instance) signs
// everyone out, which is acceptable for a console with a handful of operators; docs/integracion.md has the rest.
const IDLE_MS = 30 * 60_000
const ABSOLUTE_MS = 8 * 60 * 60_000
const MAX_SESSIONS = 200

export type OperatorSession = {
  adminKey: string // reads: queue, tickets, monitoring (X-Admin-Key)
  operatorKey?: string // acts: claim, approve, reject, release (X-Operator-Key)
  operator?: string // the name the API gave that key
  createdAt: number
  lastSeen: number
}

// On globalThis so a dev reload of this module does not drop the sessions in memory.
const holder = globalThis as { __cecilaiOperatorSessions?: Map<string, OperatorSession> }
const store = (holder.__cecilaiOperatorSessions ??= new Map<string, OperatorSession>())

const secure = process.env.NODE_ENV === 'production'
const name = secure ? '__Host-cecilai_operator' : 'cecilai_operator'
const options = { httpOnly: true, secure, sameSite: 'strict', path: '/' } as const

function alive(session: OperatorSession, now: number) {
  return now - session.lastSeen < IDLE_MS && now - session.createdAt < ABSOLUTE_MS
}

export function startOperatorSession(adminKey: string, operatorKey?: string, operator?: string) {
  const now = Date.now()
  for (const [id, session] of store) if (!alive(session, now)) store.delete(id)
  if (store.size >= MAX_SESSIONS) store.delete(store.keys().next().value!)
  const id = randomBytes(32).toString('base64url')
  store.set(id, { adminKey, operatorKey, operator, createdAt: now, lastSeen: now })
  setCookie(name, id, { ...options, maxAge: ABSOLUTE_MS / 1000 })
}

export function getOperatorSession(): OperatorSession | null {
  const id = getCookie(name)
  const session = id ? store.get(id) : undefined
  if (!id || !session) return null
  const now = Date.now()
  if (!alive(session, now)) {
    store.delete(id)
    return null
  }
  session.lastSeen = now
  return session
}

export function endOperatorSession() {
  const id = getCookie(name)
  if (id) store.delete(id)
  deleteCookie(name, options)
}
