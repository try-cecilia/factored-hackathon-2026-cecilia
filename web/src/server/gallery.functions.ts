import { createServerFn } from '@tanstack/react-start'

/** The dev gallery exists in development, or in a build started with UI_GALLERY=1. Anywhere else it is a 404. */
export const isGalleryEnabled = createServerFn({ method: 'GET' }).handler(
  (): boolean => process.env.NODE_ENV !== 'production' || process.env.UI_GALLERY === '1',
)
