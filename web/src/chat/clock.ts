import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '../i18n/context'
import { htmlLang } from '../i18n/locales'

export type TimeParts = { time: string; dateTime: string }

/**
 * Formats the hour of a message in the customer's language and in the browser's time zone. The server does not know the zone, so
 * nothing is formatted until the page has mounted: the first render (the one the server made) shows no times.
 */
export function useTimeParts(): (at: number) => TimeParts | undefined {
  const { locale } = useI18n()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const [format] = useState(() => new Map<string, Intl.DateTimeFormat>())
  return useCallback(
    (at: number) => {
      if (!mounted) return undefined
      let f = format.get(locale)
      if (!f) format.set(locale, (f = new Intl.DateTimeFormat(htmlLang[locale], { hour: '2-digit', minute: '2-digit' })))
      return { time: f.format(at), dateTime: new Date(at).toISOString() }
    },
    [mounted, locale, format],
  )
}
