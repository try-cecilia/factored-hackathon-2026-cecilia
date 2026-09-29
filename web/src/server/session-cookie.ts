import '@tanstack/react-start/server-only'
import { deleteCookie, getCookie, setCookie } from '@tanstack/react-start/server'
import { cookiePolicy } from './cookie-policy.ts'

const cookie = () => {
  const { secure, name } = cookiePolicy()
  return { name: name('cecilai_session'), options: { httpOnly: true, secure, sameSite: 'lax', path: '/' } as const }
}

export const getSessionToken = () => getCookie(cookie().name)

export const setSessionToken = (token: string, maxAge: number) => {
  const { name, options } = cookie()
  setCookie(name, token, { ...options, maxAge })
}

export const clearSessionToken = () => {
  const { name, options } = cookie()
  deleteCookie(name, options)
}
