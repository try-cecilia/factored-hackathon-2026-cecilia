import { createFileRoute, Outlet, redirect, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { getSession, logout } from '../server/auth.functions'

export const Route = createFileRoute('/_authed')({
  beforeLoad: async ({ location }) => {
    const session = await getSession()
    if (!session) throw redirect({ to: '/login', search: { redirect: location.href } })
    return { session }
  },
  errorComponent: () => (
    <main>
      <a className="brand" href="/" aria-label="Cecilai, inicio">cecilai<span>.</span></a>
      <section><p className="description">El servicio no está disponible en este momento.</p></section>
    </main>
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
    <main>
      <header className="topbar">
        <a className="brand" href="/" aria-label="Cecilai, inicio">cecilai<span>.</span></a>
        <div className="account">
          <span>Cliente {session.customer_id}</span>
          <button type="button" className="link" onClick={onLogout} disabled={loggingOut}>
            {loggingOut ? 'Saliendo…' : 'Salir'}
          </button>
        </div>
      </header>
      {logoutError && <p className="error" role="alert">No se pudo cerrar la sesión. Probá de nuevo.</p>}
      <Outlet />
    </main>
  )
}
