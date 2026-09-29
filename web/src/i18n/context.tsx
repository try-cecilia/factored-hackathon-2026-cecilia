import { createContext, use, useMemo, type ReactNode } from 'react'
import type { Locale } from './locales.ts'
import { translator, type Translate } from './translate.ts'

type I18n = { locale: Locale; t: Translate }

const I18nContext = createContext<I18n | null>(null)

export function I18nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const value = useMemo<I18n>(() => ({ locale, t: translator(locale) }), [locale])
  return <I18nContext value={value}>{children}</I18nContext>
}

export function useI18n(): I18n {
  const value = use(I18nContext)
  if (!value) throw new Error('useI18n needs an I18nProvider above it')
  return value
}

/** `const t = useT()` then `t('shell.signOut')`, or `t('shell.customer', { id })` for placeholders. */
export const useT = (): Translate => useI18n().t
