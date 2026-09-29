import type { AnyRouter } from '@tanstack/react-router'

// The console re-reads its data on a timer. Those reads must not count as the operator being present, or an abandoned
// tab keeps its session alive forever. The loaders ask `isAutomatic()` and pass it on to the server as `auto`.
let automatic = false

export const isAutomatic = () => automatic

export async function refreshQuietly(router: AnyRouter) {
  automatic = true
  try {
    await router.invalidate()
  } finally {
    automatic = false
  }
}
