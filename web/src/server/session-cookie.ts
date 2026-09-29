import '@tanstack/react-start/server-only'
import { deleteCookie, getCookie, setCookie } from '@tanstack/react-start/server'

const secure = process.env.NODE_ENV === 'production'
const name = secure ? '__Host-cecilai_session' : 'cecilai_session'
const options = { httpOnly: true, secure, sameSite: 'lax', path: '/' } as const

export const getSessionToken = () => getCookie(name)

export const setSessionToken = (token: string, maxAge: number) => setCookie(name, token, { ...options, maxAge })

export const clearSessionToken = () => deleteCookie(name, options)
