import { useSyncExternalStore } from 'react'

/** Whether a media query matches. The server renders as if it did not (the wide layout); the browser corrects it once mounted. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', notify)
      return () => list.removeEventListener('change', notify)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}
