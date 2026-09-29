import { createFileRoute, Link, Outlet, redirect, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { ChatIcon } from '../chat/icons'
import { useT } from '../i18n/context'
import { getSession, logout } from '../server/auth.functions'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'

export const Route = createFileRoute('/_authed')({
  beforeLoad: async ({ location }) => {
    const session = await getSession()
    if (!session) throw redirect({ to: '/login', search: { redirect: location.href } })
    return { session }
  },
  errorComponent: Unavailable,
  component: AuthedLayout,
})

function Unavailable() {
  const t = useT()
  return (
    <div className="sun sun-center">
      <main className="auth-card" id="main">
        <Link className="brand" to="/" aria-label={t('common.brandHome')}>
          <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
        </Link>
        <h1>{t('shell.unavailable.title')}</h1>
        <p className="lead">{t('shell.unavailable.body')}</p>
        <button type="button" className="btn btn-primary btn-lg" onClick={() => window.location.reload()}>{t('common.retry')}</button>
        <LanguageSwitcher />
      </main>
    </div>
  )
}

function AuthedLayout() {
  const { session } = Route.useRouteContext()
  const t = useT()
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
      <a className="skip" href="#main">{t('common.skipToContent')}</a>
      <div className="window">
        <aside className="sidebar">
          <Link className="brand" to="/chat" aria-label={t('common.brandHome')}>
            <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
          </Link>
          <nav aria-label={t('shell.mainNav')}>
            <Link to="/chat" className="nav-item" activeProps={{ 'aria-current': 'page' }}>
              <ChatIcon />{t('shell.nav.chat')}
            </Link>
          </nav>
          <div className="sidebar-foot">
            <div className="avatar" aria-hidden="true">{session.customer_id.slice(0, 1).toUpperCase()}</div>
            <div className="who">
              <strong>{t('shell.customer', { id: session.customer_id })}</strong>
              <span>{[session.segment, session.country].filter(Boolean).join(' · ')}</span>
            </div>
            <button type="button" className="btn btn-quiet" onClick={onLogout} disabled={loggingOut}>
              {loggingOut ? t('shell.signingOut') : t('shell.signOut')}
            </button>
            <LanguageSwitcher />
            {logoutError && <p className="error" role="alert">{t('shell.signOutFailed')}</p>}
          </div>
        </aside>
        <main className="pane" id="main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
