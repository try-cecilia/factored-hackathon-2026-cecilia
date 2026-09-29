import { createFileRoute, Outlet, redirect } from '@tanstack/react-router'
import { ConversationProvider } from '../chat/ConversationProvider'
import { useT } from '../i18n/context'
import { getSession } from '../server/auth.functions'
import { getHistory } from '../server/chat.functions'
import { getDemoKit } from '../server/demo.functions'
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
  loader: async ({ context, location }) => {
    const [history, kit] = await Promise.all([getHistory(), getDemoKit()])
    if (!history.ok && history.failure === 'session_expired') throw redirect({ to: '/login', search: { redirect: location.href } })
    return { sessionRef: context.session.session_ref, history, scenarios: kit.enabled ? kit.scenarios : null }
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
  const { sessionRef, history, scenarios } = Route.useLoaderData()
  return (
    <ConversationProvider sessionRef={sessionRef} initial={history}>
      <AppShell session={session} scenarios={scenarios}>
        <Outlet />
      </AppShell>
    </ConversationProvider>
  )
}
