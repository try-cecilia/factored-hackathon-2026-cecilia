import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router'
import stylesheet from '../styles.css?url'

export const Route = createRootRoute({
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
  component: () => (
    <html lang="es">
      <head><HeadContent /></head>
      <body><Outlet /><Scripts /></body>
    </html>
  ),
})
