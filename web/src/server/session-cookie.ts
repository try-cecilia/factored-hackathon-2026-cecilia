import '@tanstack/react-start/server-only'
import { deleteCookie, getCookie, setCookie } from '@tanstack/react-start/server'
import { cookiePolicy } from './cookie-policy.ts'
import { ReplacedSessions } from './replaced-sessions.ts'

// On globalThis so a dev reload of this module does not drop what it remembers.
const holder = globalThis as { __cecilaiReplacedSessions?: ReplacedSessions }
const replaced = (holder.__cecilaiReplacedSessions ??= new ReplacedSessions())

const cookie = () => {
  const { secure, name } = cookiePolicy()
  return { name: name('cecilai_session'), options: { httpOnly: true, secure, sameSite: 'lax', path: '/' } as const }
}

export const getSessionToken = () => getCookie(cookie().name)

// A login overwrites the cookie, and remembers which token it replaced: see `wasReplaced`.
export const setSessionToken = (token: string, maxAge: number) => {
  const { name, options } = cookie()
  const previous = getCookie(name)
  if (previous !== token) replaced.note(previous)
  setCookie(name, token, { ...options, maxAge })
}

/** Whether a login of the same browser has replaced this token since: the cookie it held is no longer the one to delete. */
export const wasReplaced = (token: string) => replaced.has(token)

export const clearSessionToken = () => {
  const { name, options } = cookie()
  deleteCookie(name, options)
}
