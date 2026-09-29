import { rootRouteId, useLoaderData } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { I18nProvider } from './context.tsx'
import type { Locale } from './locales.ts'
import type { Dictionary } from './translate.ts'

/**
 * The i18n of the page, from the root loader's data (`routes/__root.tsx`): its language and the texts of its areas. Every
 * router.invalidate() runs that loader again and brings a new copy of the same texts; structural sharing keeps the one already on
 * screen, so the translator (and whatever is memoized on it, like the queue's columns) changes only with the language or the areas.
 */
export function RootI18n({ children }: { children: ReactNode }) {
  const { locale, messages } = useLoaderData({ from: rootRouteId, structuralSharing: true }) as { locale: Locale; messages: Dictionary }
  return <I18nProvider locale={locale} messages={messages}>{children}</I18nProvider>
}
