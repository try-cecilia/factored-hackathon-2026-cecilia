import { createFileRoute, Outlet, redirect, useRouter, useRouterState } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useT } from '../i18n/context'
import { getOperatorView, loadQueue } from '../server/operator.functions'
import operatorStylesheet from '../styles/operator.css?url'
import { OperatorShell } from './-operator/OperatorShell'
import { isAutomatic, refreshQuietly } from './-operator/refresh'
import { QueueSkeleton } from './-operator/QueueSkeleton'

export const Route = createFileRoute('/_operator')({
  beforeLoad: async ({ location }) => {
    const view = await getOperatorView({ data: { auto: isAutomatic() } })
    if (view.status !== 'active') {
      throw redirect({ to: '/operador/login', search: { redirect: location.href, motivo: view.status === 'expired' ? 'vencida' : undefined } })
    }
    return { view }
  },
  // The queue is read here, not in /operador/cola: the sidebar counts come from it on every page of the console.
  loader: () => loadQueue({ data: { auto: isAutomatic() } }),
  head: () => ({
    meta: [{ name: 'robots', content: 'noindex' }],
    links: [{ rel: 'stylesheet', href: operatorStylesheet }],
  }),
  pendingMs: 300,
  pendingComponent: QueueSkeleton,
  errorComponent: Unavailable,
  component: OperatorLayout,
})

function Unavailable() {
  const t = useT()
  return (
    <div className="op">
      <main className="op-unavailable">
        <p className="op-notice" role="alert">{t('operator.unavailable')}</p>
      </main>
    </div>
  )
}

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
