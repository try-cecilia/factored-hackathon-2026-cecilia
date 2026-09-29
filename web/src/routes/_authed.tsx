import { createFileRoute, Outlet, redirect } from '@tanstack/react-router'
import { useState } from 'react'
import { ConversationProvider } from '../chat/ConversationProvider'
import { useT } from '../i18n/context'
import { getSession } from '../server/auth.functions'
import { getHistory } from '../server/chat.functions'
import { getDemoKit, type DemoKit } from '../server/demo.functions'
import { AppShell } from '../shell/AppShell'
import { PublicShell } from '../shell/PublicShell'
import { Button, PageLoader } from '../ui'

export const Route = createFileRoute('/_authed')({
  beforeLoad: async ({ location }) => {
    const session = await getSession()
    if (!session) throw redirect({ to: '/login', search: { redirect: location.href } })
    return { session }
  },
  // What the API kept of the conversation, so a reload shows it again, and whether the sandbox's panel exists.
  // The session's reference goes with its history: the two arrive together, so a new session never starts from the last one's turns.
  // The demo kit is not awaited: the chat never waits for the sandbox, only the demo's own button and panel do (AppShell). It is
  // the same for every session and language, so it is asked for on entering and a reload of this data (router.invalidate) keeps it.
  loader: async ({ context, location, cause }) => {
    const kit = cause === 'stay' ? null : getDemoKit().catch((): DemoKit => ({ enabled: false }))
    const history = await getHistory()
    if (!history.ok && history.failure === 'session_expired') throw redirect({ to: '/login', search: { redirect: location.href } })
    return { sessionRef: context.session.session_ref, history, kit }
  },
  pendingComponent: Loading,
  errorComponent: Unavailable,
  component: AuthedLayout,
})

function Loading() {
  const t = useT()
  return <PageLoader fullscreen label={t('conversation.history.loading')} />
}

function Unavailable() {
  const t = useT()
  return (
    <PublicShell>
      <main className="pub__main" id="main">
        <img className="pub__mascot" src="/cecilia-avatar.png" alt="" width={96} height={96} />
        <h1>{t('shell.unavailable.title')}</h1>
        <p className="pub__lead">{t('shell.unavailable.body')}</p>
        <Button size="lg" onClick={() => window.location.reload()}>{t('common.retry')}</Button>
      </main>
    </PublicShell>
  )
}

function AuthedLayout() {
  const { session } = Route.useRouteContext()
  const { sessionRef, history, kit: loaded } = Route.useLoaderData()
  const [kit] = useState(() => loaded ?? Promise.resolve<DemoKit>({ enabled: false }))
  return (
    <ConversationProvider sessionRef={sessionRef} initial={history}>
      <AppShell session={session} kit={kit}>
        <Outlet />
      </AppShell>
    </ConversationProvider>
  )
}
