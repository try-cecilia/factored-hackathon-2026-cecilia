import { getRouteApi } from '@tanstack/react-router'
import { Gallery } from './Gallery'

const route = getRouteApi('/dev/ui')

export function GalleryPage() {
  const { both } = route.useSearch()
  return <Gallery both={both === 1} />
}
