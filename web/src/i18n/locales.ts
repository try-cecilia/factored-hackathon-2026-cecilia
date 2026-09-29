export const locales = ['es', 'pt'] as const
export type Locale = (typeof locales)[number]

export const defaultLocale: Locale = 'es'

/** Name of each language in its own language, for the switcher: it never gets translated. */
export const localeNames: Record<Locale, string> = { es: 'Español', pt: 'Português' }

/** Value of the `lang` attribute: pt is the Brazilian variant. */
export const htmlLang: Record<Locale, string> = { es: 'es', pt: 'pt-BR' }

export const localeCookie = 'cecilai_lang'
export const localeCookieMaxAge = 60 * 60 * 24 * 365

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (locales as readonly string[]).includes(value)
}
