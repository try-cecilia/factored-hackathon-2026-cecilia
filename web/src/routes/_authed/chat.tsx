import { createFileRoute } from '@tanstack/react-router'
import { ChatView } from '../../chat/ChatView'
import { headTitle } from '../../i18n/head'

export const Route = createFileRoute('/_authed/chat')({
  head: ({ matches }) => headTitle(matches, 'shell.pageTitle.chat'),
  component: Chat,
})

function Chat() {
  const { session } = Route.useRouteContext()
  return <ChatView session={session} />
}
