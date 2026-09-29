import { createRootRoute, HeadContent, Outlet, rootRouteId, Scripts } from '@tanstack/react-router'
import { areasOf, covers, loadMessages, type Area } from '../i18n/areas'
import { I18nProvider } from '../i18n/context'
import { htmlLang } from '../i18n/locales'
import { getLocale } from '../server/locale.functions'
import stylesheet from '../styles.css?url'

export const Route = createRootRoute({
  // The language and the texts of the page's areas in it (i18n/areas.ts): they travel in this data, so the server's HTML and the
  // hydration use the same dictionary. Once per page load; again when the language changes (router.invalidate()), and when a page
  // needs an area that is not loaded yet (from the queue to the monitor), before that page is drawn.
  beforeLoad: ({ location, matches }) => {
    const loaded = matches.find((match) => match.routeId === rootRouteId)?.loaderData as { areas?: Area[] } | undefined
    return { textsMissing: !covers(loaded?.areas, areasOf(location.pathname)) }
  },
  loader: {
    handler: async ({ location }) => {
      const locale = await getLocale()
      const areas = areasOf(location.pathname)
      return { locale, areas, messages: await loadMessages(areas, locale) }
    },
    staleReloadMode: 'blocking',
  },
  shouldReload: ({ context }) => context.textsMissing,
  staleTime: Infinity,
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Cecilai' },
      { name: 'color-scheme', content: 'light' },
    ],
    links: [
      { rel: 'stylesheet', href: stylesheet },
      { rel: 'icon', type: 'image/png', href: '/cecilia-avatar.png' },
    ],
  }),
  component: RootDocument,
})

function RootDocument() {
  const { locale, messages } = Route.useLoaderData()
  return (
    <html lang={htmlLang[locale]}>
      <head><HeadContent /></head>
      <body>
        <I18nProvider locale={locale} messages={messages}><Outlet /></I18nProvider>
        <Scripts />
      </body>
    </html>
  )
}
