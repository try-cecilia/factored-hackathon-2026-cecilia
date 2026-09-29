import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router'
import { I18nProvider } from '../i18n/context'
import { htmlLang } from '../i18n/locales'
import { getLocale } from '../server/locale.functions'
import stylesheet from '../styles.css?url'

export const Route = createRootRoute({
  // Once per page load: switching language calls router.invalidate(), which runs this again.
  loader: async () => ({ locale: await getLocale() }),
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
  const { locale } = Route.useLoaderData()
  return (
    <html lang={htmlLang[locale]}>
      <head><HeadContent /></head>
      <body>
        <I18nProvider locale={locale}><Outlet /></I18nProvider>
        <Scripts />
      </body>
    </html>
  )
}
