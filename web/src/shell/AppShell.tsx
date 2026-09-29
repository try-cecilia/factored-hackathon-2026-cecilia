import { Link, useNavigate, useRouter } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { DemoPanel } from '../chat/DemoPanel'
import type { DemoScenario } from '../chat/types'
import { useConversation } from '../chat/ConversationProvider'
import { LockIcon } from '../chat/icons'
import { useT } from '../i18n/context'
import { logout, type Session } from '../server/auth.functions'
import {
  Button,
  IconButton,
  LanguageSwitcher,
  MenuIcon,
  Sidebar,
  SidebarBrand,
  SidebarChatIcon,
  SidebarPerson,
  SidebarRow,
  SidebarSection,
  SidebarSignOutIcon,
  Toast,
  ToastRegion,
} from '../ui'
import { CasesSection } from './CasesSection'
import { ShellProvider } from './ShellContext'
import { useDismiss } from './useDismiss'
import { useMediaQuery } from './useMediaQuery'
import './AppShell.css'

const PHONE = '(max-width: 759px)'
const NARROW = '(max-width: 1179px)'

/**
 * The customer's window: the sidebar (wide, or a rail, or a drawer on a phone), a bar with the page title and the language
 * switcher, the page, and, only in the demo, its own panel. Everything that changes with the conversation reads it from the provider.
 */
export function AppShell({ session, scenarios, children }: { session: Session; scenarios: DemoScenario[] | null; children: ReactNode }) {
  const t = useT()
  const navigate = useNavigate()
  const router = useRouter()
  const { cases, entries, sending, send } = useConversation()
  const phone = useMediaQuery(PHONE)
  const narrow = useMediaQuery(NARROW)
  const [collapsed, setCollapsed] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  // Wide screens show the demo panel from the start; narrow ones keep it behind its button until the reader asks.
  const [demoChoice, setDemoChoice] = useState<boolean | null>(null)
  const demoOpen = scenarios !== null && (demoChoice ?? !narrow)
  const setDemoOpen = useCallback((next: boolean | ((open: boolean) => boolean)) => setDemoChoice((current) => (typeof next === 'function' ? next(current ?? !narrow) : next)), [narrow])
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutFailed, setLogoutFailed] = useState(false)
  const side = useRef<HTMLDivElement>(null)
  const demo = useRef<HTMLDivElement>(null)

  useDismiss(menuOpen, phone, () => setMenuOpen(false), side)
  useDismiss(demoOpen, narrow, () => setDemoOpen(false), demo)
  // Leaving the phone size closes the drawer that no longer exists.
  useEffect(() => {
    if (!phone) setMenuOpen(false)
  }, [phone])

  const openCase = useCallback((ticketId: string) => {
    setMenuOpen(false)
    // The handoff message is the case: bring it into view and leave the focus on it.
    const message = document.getElementById(`case-msg-${ticketId}`)
    message?.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    message?.focus({ preventScroll: true })
  }, [])

  const showCase = useCallback((ticketId: string) => {
    setMenuOpen(true)
    setCollapsed(false)
    requestAnimationFrame(() => document.getElementById(`case-row-${ticketId}`)?.focus())
  }, [])

  async function onLogout() {
    setLoggingOut(true)
    setLogoutFailed(false)
    try {
      await logout()
      await navigate({ to: '/login' })
    } catch {
      setLogoutFailed(true)
    } finally {
      setLoggingOut(false)
    }
  }

  const rail = collapsed && !phone
  const escalations = entries.filter((e) => e.role === 'assistant' && e.reply.disposition === 'ESCALATE').length
  const detail = [session.segment, session.country].filter(Boolean).join(' · ')

  return (
    <ShellProvider value={{ showCase }}>
      <a className="skip" href="#main">{t('common.skipToContent')}</a>
      <div className="shell" data-menu={menuOpen ? 'open' : undefined} data-demo={demoOpen ? 'open' : undefined}>
        <div
          id="shell-side"
          ref={side}
          className="shell__side"
          role={phone && menuOpen ? 'dialog' : undefined}
          aria-modal={phone && menuOpen ? true : undefined}
          aria-label={phone && menuOpen ? t('shell.mainNav') : undefined}
          inert={phone && !menuOpen ? true : undefined}
        >
          {phone && (
            <IconButton
              className="shell__close"
              variant="ghost"
              size="sm"
              label={t('shell.menu.close')}
              icon={<svg viewBox="0 0 20 20" width={14} height={14} aria-hidden="true" focusable="false"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" /></svg>}
              onClick={() => setMenuOpen(false)}
            />
          )}
          <Sidebar
            collapsed={rail}
            onCollapsedChange={phone ? undefined : setCollapsed}
            label={t('shell.mainNav')}
            header={<SidebarBrand />}
            footer={
              <>
                <SidebarSection>
                  <SidebarRow
                    icon={<SidebarSignOutIcon />}
                    label={loggingOut ? t('shell.signingOut') : t('shell.signOut')}
                    disabled={loggingOut}
                    onClick={() => void onLogout()}
                  />
                </SidebarSection>
                <SidebarPerson name={t('shell.customer', { id: session.customer_id })} detail={detail} />
              </>
            }
          >
            <SidebarSection>
              <SidebarRow as={Link} to="/chat" active icon={<SidebarChatIcon />} label={t('shell.nav.chat')} />
            </SidebarSection>
            <CasesSection cases={cases} collapsed={rail} onOpen={openCase} onExpand={() => setCollapsed(false)} />
          </Sidebar>
        </div>
        {phone && menuOpen && <button type="button" className="shell__scrim" aria-label={t('shell.menu.scrim')} onClick={() => setMenuOpen(false)} />}

        <div className="shell__main">
          <header className="shell__bar">
            <IconButton
              className="shell__menu"
              variant="ghost"
              size="md"
              label={menuOpen ? t('shell.menu.close') : t('shell.menu.open')}
              icon={<MenuIcon size={16} />}
              aria-expanded={menuOpen}
              aria-controls="shell-side"
              onClick={() => setMenuOpen((open) => !open)}
            />
            <h1 className="shell__title">{t('conversation.title')}</h1>
            <span className="shell__trust"><LockIcon />{t('conversation.trust')}</span>
            <div className="shell__tools">
              {scenarios && (
                <Button
                  variant="ghost"
                  size="sm"
                  tinted={demoOpen}
                  aria-expanded={demoOpen}
                  aria-controls="shell-demo"
                  onClick={() => setDemoOpen((open) => !open)}
                >
                  {t('shell.demo.toggle')}
                </Button>
              )}
              <LanguageSwitcher />
            </div>
          </header>
          <main className="shell__page" id="main">{children}</main>
        </div>

        {scenarios && (
          <>
            {narrow && demoOpen && <button type="button" className="shell__scrim shell__scrim--demo" aria-label={t('shell.demo.hide')} onClick={() => setDemoOpen(false)} />}
            <div
              id="shell-demo"
              ref={demo}
              className="shell__demo"
              role={narrow && demoOpen ? 'dialog' : undefined}
              aria-modal={narrow && demoOpen ? true : undefined}
              aria-label={narrow && demoOpen ? t('demo.panel') : undefined}
              inert={!demoOpen ? true : undefined}
            >
              <DemoPanel
                scenarios={scenarios}
                sessionRef={session.session_ref}
                pending={sending}
                escalations={escalations}
                send={send}
                onSessionChanged={() => router.invalidate()}
                onClose={() => setDemoOpen(false)}
              />
            </div>
          </>
        )}
      </div>
      <ToastRegion>{logoutFailed && <Toast variant="error" onClose={() => setLogoutFailed(false)}>{t('shell.signOutFailed')}</Toast>}</ToastRegion>
    </ShellProvider>
  )
}
