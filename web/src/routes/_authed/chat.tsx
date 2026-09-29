import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/_authed/chat')({
  head: () => ({ meta: [{ title: 'Chat · Cecilai' }] }),
  component: Chat,
})

function Chat() {
  const { session } = Route.useRouteContext()
  const minutes = Math.max(1, Math.ceil(session.expires_in / 60))

  return (
    <section>
      <p className="eyebrow">Chat — próximamente</p>
      <h1>Ya estás adentro.</h1>
      <p className="description">
        Segmento {session.segment} · {session.country}. Tu sesión vence en {minutes} {minutes === 1 ? 'minuto' : 'minutos'}.
      </p>
    </section>
  )
}
