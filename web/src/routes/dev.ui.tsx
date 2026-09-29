import { createFileRoute, lazyRouteComponent, notFound } from '@tanstack/react-router'
import { isGalleryEnabled } from '../server/gallery.functions'

export const Route = createFileRoute('/dev/ui')({
  validateSearch: (search: Record<string, unknown>): { both?: 1 } => (search.both === 1 || search.both === '1' ? { both: 1 } : {}),
  beforeLoad: async () => {
    if (!(await isGalleryEnabled())) throw notFound()
  },
  head: () => ({ meta: [{ title: 'UI kit · Cecilai' }, { name: 'robots', content: 'noindex' }] }),
  // Its own chunk: the gallery is not part of what the customer downloads.
  component: lazyRouteComponent(async () => {
    const { GalleryPage } = await import('../ui/gallery/GalleryPage')
    return { default: GalleryPage }
  }),
})
