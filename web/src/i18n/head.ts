import { defaultLocale, isLocale, type Locale } from './locales.ts'
import { translate, type MessageKey, type Params } from './translate.ts'

/** For a route's `head()`: the locale the root loader resolved, and a translated title. */
export function headTitle(matches: ReadonlyArray<{ routeId: string; loaderData?: unknown }>, key: MessageKey, params?: Params) {
  const root = matches.find((match) => match.routeId === '__root__')?.loaderData as { locale?: unknown } | undefined
  const locale: Locale = isLocale(root?.locale) ? root.locale : defaultLocale
  return { meta: [{ title: translate(locale, key, params) }] }
}
