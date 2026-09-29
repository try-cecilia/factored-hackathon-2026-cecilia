import { createServerFn } from '@tanstack/react-start'
import { getCookie, getRequestHeader, setCookie } from '@tanstack/react-start/server'
import { isLocale, localeCookie, localeCookieMaxAge, type Locale } from '../i18n/locales.ts'
import { resolveLocale } from '../i18n/resolve.ts'
import { cookiePolicy } from './cookie-policy.ts'

/** Cookie first, then Accept-Language, then Spanish; resolved on the server so the SSR comes out in the right language. */
export const getLocale = createServerFn({ method: 'GET' }).handler(
  (): Locale => resolveLocale({ cookie: getCookie(localeCookie), acceptLanguage: getRequestHeader('accept-language') }),
)

function parseLocale(input: unknown): Locale {
  if (!isLocale(input)) throw new Error('unsupported locale')
  return input
}

/** The preference is not a secret nor a session: readable by the browser, one year, same site. */
export const setLocale = createServerFn({ method: 'POST' })
  .validator(parseLocale)
  .handler(({ data }) => {
    setCookie(localeCookie, data, { path: '/', maxAge: localeCookieMaxAge, sameSite: 'lax', secure: cookiePolicy().secure })
  })
