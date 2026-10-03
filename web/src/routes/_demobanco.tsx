import { createFileRoute, Outlet, redirect, useRouter } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import type { DemoTrace } from '../chat/types'
import { getDemoDeskView, loadDemoQueue, type DemoDeskView } from '../server/demo-desk.functions'
import { demoEntries } from '../server/demo-entry'
import { getDemoKit, getDemoTraces, type DemoKit } from '../server/demo.functions'
import operatorStylesheet from '../styles/operator.css?url'
import { DemoBar } from './-demo/DemoBar'
import { DemoDeskShell } from './-demo/DemoDeskShell'
import { DemoExpired } from './-demo/DemoExpired'
import './-demo/demo-desk.css'
import { QueueSkeleton } from './-operator/QueueSkeleton'
import { guarded } from './-operator/reload'
import { Unavailable } from './-operator/Unavailable'

type Desk = Extract<DemoDeskView, { status: 'active' }> | { status: 'expired' }

export const Route = createFileRoute('/_demobanco')({
  // Without the demo console the bank's side does not exist; without a session it starts at the landing ("Probar la demo"). A session that ends
  // while the visitor is here (the 30-second refresh finds it gone) stays on screen and says so, with the way back in.
  beforeLoad: async ({ cause }): Promise<{ desk: Desk }> => {
    // Off, the function is an HTTP 404: a Response where it runs in the server's render, an Error with its text in the browser.
    const view = await getDemoDeskView().catch((error: unknown) => {
      if ((error instanceof Response && error.status === 404) || (error instanceof Error && error.message === 'Not Found')) throw redirect({ to: '/' })
      throw error
    })
    if (view.status === 'no_session') {
      if (cause === 'stay') return { desk: { status: 'expired' } }
      throw redirect({ to: '/' })
    }
    return { desk: view }
  },
  loader: async ({ context }) => {
    if (context.desk.status !== 'active') return { queue: null, traces: [] as DemoTrace[], kit: { enabled: false } as DemoKit }
    const [queue, traces, kit] = await Promise.all([
      guarded(() => loadDemoQueue()),
      getDemoTraces().catch((): DemoTrace[] => []),
      getDemoKit().catch((): DemoKit => ({ enabled: false })),
    ])
    return { queue, traces, kit }
  },
  head: () => ({
    meta: [{ name: 'robots', content: 'noindex' }],
    links: [{ rel: 'stylesheet', href: operatorStylesheet }],
  }),
  pendingMs: 300,
  pendingComponent: QueueSkeleton,
  errorComponent: Unavailable,
  component: DemoBankLayout,
})

const REFRESH_MS = 30_000

function DemoBankLayout() {
  const { desk } = Route.useRouteContext()
  const { queue, traces, kit } = Route.useLoaderData({ structuralSharing: true })
  const router = useRouter()
  // Who this visitor entered as, kept past the end of the session: "enter again" signs in as the same test customer.
  const role = useRef<ReturnType<typeof demoEntries>[number]['role'] | null>(null)
  if (desk.status === 'active') role.current = demoEntries(kit).find((e) => e.customer_id === desk.customerId)?.role ?? role.current

  // New cases of the customer's side and their state re-read themselves while the tab is visible.
  useEffect(() => {
    if (desk.status !== 'active') return
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void router.invalidate()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [router, desk.status])

  const active = desk.status === 'active'
  // A session the API stopped taking between two reads (401) is over too.
  const over = !active || (queue && !queue.ok && (queue.status === 401 || queue.status === 0))
  return (
    <div className="op demo-frame">
      <DemoBar view="bank" sessionRef={active ? desk.sessionRef : null} expiresIn={active ? desk.expiresIn : null} ended={Boolean(over)} role={role.current} />
      <DemoDeskShell cases={queue?.ok ? queue.data.length : null} traces={active ? traces.length : null}>
        {over ? <div className="demo-desk__over"><DemoExpired role={role.current} /></div> : <Outlet />}
      </DemoDeskShell>
    </div>
  )
}
