import { Link, useNavigate, useRouter } from '@tanstack/react-router'
import { lazy, Suspense, use, useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { DemoScenario } from '../chat/types'
import { useConversation } from '../chat/ConversationProvider'
import { LockIcon } from '../chat/icons'
import { useT } from '../i18n/context'
import { logout, type Session } from '../server/auth.functions'
import type { DemoKit } from '../server/demo.functions'
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
// Only its code waits for the panel: its styles come now, so a panel drawn by the server is never unstyled.
import '../chat/DemoPanel.css'

// DEMO_MODE only: the chat never downloads it without the sandbox.
const DemoPanel = lazy(() => import('../chat/DemoPanel').then((m) => ({ default: m.DemoPanel })))

const PHONE = '(max-width: 759px)'
const NARROW = '(max-width: 1179px)'

/**
 * The customer's window: the sidebar (wide, or a rail, or a drawer on a phone), a bar with the page title and the language
 * switcher, the page, and, only in the demo, its own panel. Everything that changes with the conversation reads it from the provider.
 * The demo's button and panel wait for the kit on their own: the rest of the window is drawn without it.
 */
export function AppShell({ session, kit, children }: { session: Session; kit: Promise<DemoKit>; children: ReactNode }) {
  const t = useT()
  const navigate = useNavigate()
  const router = useRouter()
  const { cases, entries, sending, send } = useConversation()
  const phone = useMediaQuery(PHONE)
  const narrow = useMediaQuery(NARROW)
  const [collapsed, setCollapsed] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  // Wide screens show the demo panel from the start; narrow ones keep it behind its button until the reader asks. Without the
  // sandbox there is neither panel nor button, so on a narrow screen it can never be opened.
  const [demoChoice, setDemoChoice] = useState<boolean | null>(null)
  const demoOpen = demoChoice ?? !narrow
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
  // While a panel slides over the page it is modal: everything behind it is inert, and the focus stays inside it.
  const menuModal = phone && menuOpen
  const demoModal = narrow && demoOpen
  const behind = menuModal || demoModal
  const escalations = entries.filter((e) => e.role === 'assistant' && e.reply.disposition === 'ESCALATE').length
  const detail = [session.segment, session.country].filter(Boolean).join(' · ')

  return (
    <ShellProvider value={{ showCase }}>
      <a className="skip" href="#main" inert={behind ? true : undefined}>{t('common.skipToContent')}</a>
      <div className="shell" data-menu={menuOpen ? 'open' : undefined} data-demo={demoOpen ? 'open' : undefined}>
        <div
          id="shell-side"
          ref={side}
          className="shell__side"
          role={phone && menuOpen ? 'dialog' : undefined}
          aria-modal={phone && menuOpen ? true : undefined}
          aria-label={phone && menuOpen ? t('shell.mainNav') : undefined}
          inert={(phone && !menuOpen) || demoModal ? true : undefined}
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
        {phone && menuOpen && <button type="button" tabIndex={-1} className="shell__scrim" aria-label={t('shell.menu.scrim')} onClick={() => setMenuOpen(false)} />}

        <div className="shell__main" inert={behind ? true : undefined}>
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
              <Suspense fallback={null}>
                <DemoToggle kit={kit} open={demoOpen} onToggle={() => setDemoOpen((open) => !open)} />
              </Suspense>
              <LanguageSwitcher />
            </div>
          </header>
          <main className="shell__page" id="main">{children}</main>
        </div>

        <Suspense fallback={null}>
          <DemoColumn kit={kit} panel={demo} open={demoOpen} narrow={narrow} inert={!demoOpen || menuModal} onClose={() => setDemoOpen(false)}>
            {(scenarios) => (
              <DemoPanel
                scenarios={scenarios}
                sessionRef={session.session_ref}
                pending={sending}
                escalations={escalations}
                send={send}
                onSessionChanged={() => router.invalidate()}
                onClose={() => setDemoOpen(false)}
              />
            )}
          </DemoColumn>
        </Suspense>
      </div>
      <ToastRegion>{logoutFailed && <Toast variant="error" onClose={() => setLogoutFailed(false)}>{t('shell.signOutFailed')}</Toast>}</ToastRegion>
    </ShellProvider>
  )
}

function DemoToggle({ kit, open, onToggle }: { kit: Promise<DemoKit>; open: boolean; onToggle: () => void }) {
  const t = useT()
  if (!use(kit).enabled) return null
  return (
    <Button variant="ghost" size="sm" tinted={open} aria-expanded={open} aria-controls="shell-demo" onClick={onToggle}>
      {t('shell.demo.toggle')}
    </Button>
  )
}

function DemoColumn({ kit, panel, open, narrow, inert, onClose, children }: {
  kit: Promise<DemoKit>
  panel: RefObject<HTMLDivElement | null>
  open: boolean
  narrow: boolean
  inert: boolean
  onClose: () => void
  children: (scenarios: DemoScenario[]) => ReactNode
}) {
  const t = useT()
  const resolved = use(kit)
  if (!resolved.enabled) return null
  return (
    <>
      {narrow && open && <button type="button" tabIndex={-1} className="shell__scrim shell__scrim--demo" aria-label={t('shell.demo.hide')} onClick={onClose} />}
      <div
        id="shell-demo"
        ref={panel}
        className="shell__demo"
        role={narrow && open ? 'dialog' : undefined}
        aria-modal={narrow && open ? true : undefined}
        aria-label={narrow && open ? t('demo.panel') : undefined}
        inert={inert ? true : undefined}
      >
        <Suspense fallback={null}>{children(resolved.scenarios)}</Suspense>
      </div>
    </>
  )
}
