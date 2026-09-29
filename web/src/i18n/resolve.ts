import { defaultLocale, isLocale, locales, type Locale } from './locales.ts'

type Weighted = { tag: string; q: number }

function parseAcceptLanguage(header: string): Weighted[] {
  const items: Weighted[] = []
  for (const part of header.split(',')) {
    const [range, ...params] = part.trim().split(';')
    const tag = range?.trim().toLowerCase()
    if (!tag) continue
    let q = 1
    for (const param of params) {
      const [key, value] = param.trim().split('=')
      if (key?.trim().toLowerCase() === 'q') q = Number(value)
    }
    if (Number.isFinite(q) && q > 0) items.push({ tag, q })
  }
  // A stable sort keeps the order the browser sent among equal weights.
  return items.sort((a, b) => b.q - a.q)
}

/** The supported locale for a language range like `pt-BR` or `es`, or undefined (`*` and unknown languages). */
function localeOfTag(tag: string): Locale | undefined {
  const primary = tag.split('-')[0]
  return locales.find((locale) => locale === primary)
}

export function localeFromAcceptLanguage(header: string | null | undefined): Locale | undefined {
  if (!header) return undefined
  for (const { tag } of parseAcceptLanguage(header)) {
    const locale = localeOfTag(tag)
    if (locale) return locale
  }
  return undefined
}

/** Server-side resolution, in this order: preference cookie, then Accept-Language, then the default. */
export function resolveLocale(input: { cookie?: string | null; acceptLanguage?: string | null }): Locale {
  if (isLocale(input.cookie)) return input.cookie
  return localeFromAcceptLanguage(input.acceptLanguage) ?? defaultLocale
}
