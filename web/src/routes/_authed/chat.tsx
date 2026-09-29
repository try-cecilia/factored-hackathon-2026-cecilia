import { createFileRoute } from '@tanstack/react-router'
import { ChatView } from '../../chat/ChatView'
import { headTitle } from '../../i18n/head'
import { getDemoKit } from '../../server/demo.functions'

export const Route = createFileRoute('/_authed/chat')({
  loader: () => getDemoKit(),
  head: ({ matches }) => headTitle(matches, 'shell.pageTitle.chat'),
  component: Chat,
})

function Chat() {
  const { session } = Route.useRouteContext()
  const kit = Route.useLoaderData()
  return <ChatView session={session} scenarios={kit.enabled ? kit.scenarios : null} />
}
