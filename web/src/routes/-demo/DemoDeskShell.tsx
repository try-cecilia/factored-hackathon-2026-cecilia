import { Link, useRouterState } from '@tanstack/react-router'
import { useEffect, useState, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { IconButton, LanguageSwitcher, MenuIcon, Sidebar, SidebarBrand, SidebarRow, SidebarSection } from '../../ui'

/**
 * The bank's side of the one-click demo (Paper "Demo 3 · Como banco"): the console's frame cut down to this visitor's cases and
 * traces. No queues of others, no monitoring, no traces of the assistant, no audit: the note at the bottom says so.
 */
export function DemoDeskShell({ cases, traces, children }: { cases: number | null; traces: number | null; children: ReactNode }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const onTraces = pathname.startsWith('/demo/banco/rastreos')

  // The drawer of small screens closes when the visitor picks something, and with Escape.
  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div className="op-shell demo-desk" data-nav={open ? 'open' : undefined}>
      {/* In a landmark of its own, so nothing of the page is outside one (axe, region). */}
      <nav className="demo-skip" aria-label={t('demoMode.desk.nav.skip')}><a className="skip" href="#contenido">{t('operator.skip')}</a></nav>
      <header className="op-topbar">
        <IconButton variant="ghost" size="sm" label={open ? t('demoMode.desk.nav.closeMenu') : t('demoMode.desk.nav.menu')} aria-expanded={open} aria-controls="op-side" icon={<MenuIcon />} onClick={() => setOpen((v) => !v)} />
        <span className="op-topbar__brand">cecilai <span>{t('demoMode.desk.brand')}</span></span>
      </header>
      {open && <button type="button" className="op-scrim" aria-label={t('demoMode.desk.nav.closeMenu')} tabIndex={-1} onClick={() => setOpen(false)} />}
      <div className="op-side" id="op-side">
        <Sidebar
          variant="operator"
          label={t('demoMode.desk.nav.label')}
          header={<SidebarBrand product={t('demoMode.desk.brand')} />}
          footer={
            <div className="op-side__foot demo-desk__foot">
              <p className="demo-desk__note">{t('demoMode.desk.note')}</p>
              <LanguageSwitcher />
            </div>
          }
        >
          <SidebarSection>
            <SidebarRow as={Link} to="/demo/banco" label={t('demoMode.desk.nav.cases')} active={!onTraces} meta={cases === null ? undefined : String(cases)} />
            <SidebarRow as={Link} to="/demo/banco/rastreos" label={t('demoMode.desk.nav.traces')} active={onTraces} meta={traces === null ? undefined : String(traces)} />
          </SidebarSection>
        </Sidebar>
      </div>
      <main className="op-main" id="contenido" tabIndex={-1}>
        {children}
      </main>
    </div>
  )
}
