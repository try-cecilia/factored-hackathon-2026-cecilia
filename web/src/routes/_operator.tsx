import { createFileRoute, Outlet, redirect, useRouter, useRouterState } from '@tanstack/react-router'
import { useEffect } from 'react'
import { getOperatorView, loadQueue } from '../server/operator.functions'
import operatorStylesheet from '../styles/operator.css?url'
import { OperatorShell } from './-operator/OperatorShell'
import { isAutomatic, refreshQuietly } from './-operator/refresh'
import { guarded } from './-operator/reload'
import { QueueSkeleton } from './-operator/QueueSkeleton'
import { Unavailable } from './-operator/Unavailable'

export const Route = createFileRoute('/_operator')({
  beforeLoad: async ({ location }) => {
    const view = await getOperatorView({ data: { auto: isAutomatic() } })
    if (view.status !== 'active') {
      throw redirect({ to: '/operador/login', search: { redirect: location.href, motivo: view.status === 'expired' ? 'vencida' : undefined } })
    }
    return { view }
  },
  // The queue is read here, not in /operador/cola: the sidebar counts come from it on every page of the console.
  // `guarded`: a read that cannot even leave the browser is an error result, not a route error that would replace the whole console.
  loader: () => guarded(() => loadQueue({ data: { auto: isAutomatic() } })),
  head: () => ({
    meta: [{ name: 'robots', content: 'noindex' }],
    links: [{ rel: 'stylesheet', href: operatorStylesheet }],
  }),
  pendingMs: 300,
  pendingComponent: QueueSkeleton,
  errorComponent: Unavailable,
  component: OperatorLayout,
})

const REFRESH_MS = 30_000

function OperatorLayout() {
  const { view } = Route.useRouteContext()
  const queue = Route.useLoaderData()
  const router = useRouter()
  const watching = useRouterState({ select: (s) => /^\/operador\/(cola|trazas)/.test(s.location.pathname) })

  // The queue and the traces re-read themselves. That read must not count as the operator being present (see refresh.ts),
  // and it is read with `isAutomatic()` above. The monitoring page has its own, slower timer.
  useEffect(() => {
    if (!watching) return
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void refreshQuietly(router)
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [router, watching])
  return (
    <div className="op">
      <OperatorShell view={view} queue={queue}>
        <Outlet />
      </OperatorShell>
    </div>
  )
}
