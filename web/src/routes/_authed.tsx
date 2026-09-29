import { createFileRoute, Link, Outlet, redirect, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { ChatIcon } from '../chat/icons'
import { getSession, logout } from '../server/auth.functions'

export const Route = createFileRoute('/_authed')({
  beforeLoad: async ({ location }) => {
    const session = await getSession()
    if (!session) throw redirect({ to: '/login', search: { redirect: location.href } })
    return { session }
  },
  errorComponent: () => (
    <div className="sun sun-center">
      <main className="auth-card" id="main">
        <Link className="brand" to="/" aria-label="Cecilai, inicio">
          <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
        </Link>
        <h1>Servicio no disponible.</h1>
        <p className="lead">No pudimos conectar con el servicio en este momento. Probá de nuevo en unos minutos.</p>
        <button type="button" className="btn btn-primary btn-lg" onClick={() => window.location.reload()}>Reintentar</button>
      </main>
    </div>
  ),
  component: AuthedLayout,
})

function AuthedLayout() {
  const { session } = Route.useRouteContext()
  const navigate = useNavigate()
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState(false)

  async function onLogout() {
    setLoggingOut(true)
    setLogoutError(false)
    try {
      await logout()
      await navigate({ to: '/login' })
    } catch {
      setLogoutError(true)
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <div className="sun">
      <a className="skip" href="#main">Saltar al contenido</a>
      <div className="window">
        <aside className="sidebar">
          <Link className="brand" to="/chat" aria-label="Cecilai, inicio">
            <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
          </Link>
          <nav aria-label="Principal">
            <Link to="/chat" className="nav-item" activeProps={{ 'aria-current': 'page' }}>
              <ChatIcon />Chat
            </Link>
          </nav>
          <div className="sidebar-foot">
            <div className="avatar" aria-hidden="true">{session.customer_id.slice(0, 1).toUpperCase()}</div>
            <div className="who">
              <strong>Cliente {session.customer_id}</strong>
              <span>{[session.segment, session.country].filter(Boolean).join(' · ')}</span>
            </div>
            <button type="button" className="btn btn-quiet" onClick={onLogout} disabled={loggingOut}>
              {loggingOut ? 'Saliendo…' : 'Salir'}
            </button>
            {logoutError && <p className="error" role="alert">No se pudo cerrar la sesión. Probá de nuevo.</p>}
          </div>
        </aside>
        <main className="pane" id="main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
