import { Link, useNavigate, useRouter } from '@tanstack/react-router'
import { lazy, Suspense, use, useCallback, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from 'react'
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
import { CaseView } from './CaseView'
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
 * switcher, the page, the view of a case over it, and, only in the demo, its own panel. Everything that changes with the conversation
 * reads it from the provider.
 * The demo's button and panel wait for the kit on their own: the rest of the window is drawn without it.
 */
export function AppShell({ session, kit, children }: { session: Session; kit: Promise<DemoKit>; children: ReactNode }) {
  const t = useT()
  const navigate = useNavigate()
  const router = useRouter()
  const { sessionRef, cases, entries, sending, ended, send, refreshCase } = useConversation()
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
  // The case being looked at. `open` slides the view in; the case stays while it slides out, and `seen` counts the openings, so
  // opening the same case again asks for it again. It belongs to the session it was opened in: another session (a Demo scenario
  // signs in as another customer) has neither that case nor its view.
  const [opened, setCaseView] = useState<{ id: string; open: boolean; seen: number; session: string } | null>(null)
  const caseView = opened?.session === session.session_ref ? opened : null
  const caseOpen = caseView?.open ?? false
  const caseTitle = useId()
  const side = useRef<HTMLDivElement>(null)
  const demo = useRef<HTMLDivElement>(null)
  const casePanel = useRef<HTMLDivElement>(null)

  const closeCase = useCallback(() => setCaseView((view) => view && { ...view, open: false }), [])
  useDismiss(menuOpen, phone, () => setMenuOpen(false), side)
  // Reopened with a scenario in course, the drawer opens on its card (with the steps) and not at the top of the list.
  useDismiss(demoOpen, narrow, () => setDemoOpen(false), demo, undefined, () => demo.current?.querySelector<HTMLElement>('[data-active-scenario]') ?? null)
  // Always modal, on every screen: the view is over the page, and Escape gives the focus back to what opened it.
  // Opened from the phone drawer's row, the drawer closes at once: the focus comes back to the menu button instead.
  useDismiss(caseOpen, true, closeCase, casePanel, () => document.getElementById('shell-menu'))
  // Leaving the phone size closes the drawer that no longer exists.
  useEffect(() => {
    if (!phone) setMenuOpen(false)
  }, [phone])

  // "Ver caso" in a handoff message and a case's row in the sidebar open the case's view (on a phone the drawer closes first).
  const showCase = useCallback((ticketId: string) => {
    setMenuOpen(false)
    setCaseView((view) => ({ id: ticketId, open: true, seen: (view?.seen ?? 0) + 1, session: session.session_ref }))
  }, [session.session_ref])

  // From the view back to the conversation: the handoff message comes into view with the focus on it, once the view has closed
  // and handed the focus back.
  const showInChat = useCallback((ticketId: string) => {
    closeCase()
    requestAnimationFrame(() => {
      const message = document.getElementById(`case-msg-${ticketId}`)
      message?.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
      message?.focus({ preventScroll: true })
    })
  }, [closeCase])

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
  const behind = menuModal || demoModal || caseOpen
  const inChat = (ticketId: string) => entries.some((e) => e.role === 'assistant' && e.reply.disposition === 'ESCALATE' && e.reply.ticket_id === ticketId)
  const escalations = entries.filter((e) => e.role === 'assistant' && e.reply.disposition === 'ESCALATE').length
  const detail = [session.segment, session.country].filter(Boolean).join(' · ')

  return (
    <ShellProvider value={{ showCase }}>
      <a className="skip" href="#main" inert={behind ? true : undefined}>{t('common.skipToContent')}</a>
      <div className="shell" data-menu={menuOpen ? 'open' : undefined} data-demo={demoOpen ? 'open' : undefined} data-case={caseOpen ? 'open' : undefined}>
        <div
          id="shell-side"
          ref={side}
          className="shell__side"
          role={phone && menuOpen ? 'dialog' : undefined}
          aria-modal={phone && menuOpen ? true : undefined}
          aria-label={phone && menuOpen ? t('shell.mainNav') : undefined}
          inert={(phone && !menuOpen) || demoModal || caseOpen ? true : undefined}
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
            <CasesSection cases={cases} collapsed={rail} onOpen={showCase} onExpand={() => setCollapsed(false)} />
          </Sidebar>
        </div>
        {phone && menuOpen && <button type="button" tabIndex={-1} className="shell__scrim" aria-label={t('shell.menu.scrim')} onClick={() => setMenuOpen(false)} />}

        <div className="shell__main" inert={behind ? true : undefined}>
          <header className="shell__bar">
            <IconButton
              id="shell-menu"
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
          <DemoColumn kit={kit} panel={demo} open={demoOpen} narrow={narrow} inert={!demoOpen || menuModal || caseOpen} onClose={() => setDemoOpen(false)}>
            {(scenarios) => (
              <DemoPanel
                scenarios={scenarios}
                sessionRef={sessionRef}
                entries={entries}
                pending={sending}
                escalations={escalations}
                ended={ended}
                send={send}
                overlay={narrow}
                onSessionChanged={() => router.invalidate()}
                onClose={() => setDemoOpen(false)}
              />
            )}
          </DemoColumn>
        </Suspense>

        {caseOpen && <button type="button" tabIndex={-1} className="shell__scrim shell__scrim--case" aria-label={t('cases.detail.close')} onClick={closeCase} />}
        <div
          id="shell-case"
          ref={casePanel}
          className="shell__case"
          role={caseOpen ? 'dialog' : undefined}
          aria-modal={caseOpen ? true : undefined}
          aria-labelledby={caseOpen ? caseTitle : undefined}
          inert={caseOpen ? undefined : true}
        >
          {caseView && (
            <CaseView
              key={`${caseView.id}-${caseView.seen}`}
              ticketId={caseView.id}
              row={cases.find((c) => c.ref.ticketId === caseView.id)}
              ended={ended}
              titleId={caseTitle}
              refresh={refreshCase}
              onClose={closeCase}
              onShowInChat={inChat(caseView.id) ? showInChat : undefined}
            />
          )}
        </div>
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
