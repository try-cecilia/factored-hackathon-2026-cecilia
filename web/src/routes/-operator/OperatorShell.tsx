import { Link, useRouterState } from '@tanstack/react-router'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import type { OperatorView, QueueRow, Result } from '../../server/operator.functions'
import { IconButton, LanguageSwitcher, MenuIcon, Sidebar, SidebarBrand, SidebarPerson, SidebarRow, SidebarSection } from '../../ui'
import { NewCasesAnnouncer, NewCasesBadge } from './NewCases'
import { OperatorKeyForm } from './OperatorKeyForm'
import { sidebarCounts, type QueueSearch } from './queue'

type Active = Extract<OperatorView, { status: 'active' }>

// `SidebarRow as={Link}` keeps the router's generics out of the kit, so the search of these links is checked here instead.
const toQueue = (search: QueueSearch) => ({ to: '/operador/cola', search: search as never })

/** Compact operator sidebar (Paper "Operator · Queue"): views, the seven queues, the records, and who is signed in. */
export function OperatorShell({ view, queue, children }: { view: Active; queue: Result<QueueRow[]>; children: ReactNode }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const location = useRouterState({ select: (s) => s.location })
  const counts = useMemo(() => (queue.ok ? sidebarCounts(queue.data, view.operator) : null), [queue, view.operator])

  const onQueue = location.pathname.startsWith('/operador/cola')
  const search = location.search as { vista?: string; cola?: string }
  const plain = onQueue && !search.vista && !search.cola
  const count = (n: number | undefined) => (n === undefined ? undefined : String(n))

  // The drawer of small screens closes when the operator picks something, and with Esc.
  const place = `${location.pathname}?${location.searchStr}`
  useEffect(() => setOpen(false), [place])
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div className="op-shell" data-nav={open ? 'open' : undefined}>
      <a className="skip" href="#contenido">{t('operator.skip')}</a>
      <header className="op-topbar">
        <IconButton variant="ghost" size="sm" label={open ? t('operator.nav.closeMenu') : t('operator.nav.menu')} aria-expanded={open} aria-controls="op-side" icon={<MenuIcon />} onClick={() => setOpen((v) => !v)} />
        <span className="op-topbar__brand">cecilai <span>{t('sidebar.brand.operations')}</span></span>
      </header>
      {open && <button type="button" className="op-scrim" aria-label={t('operator.nav.closeMenu')} tabIndex={-1} onClick={() => setOpen(false)} />}
      <div className="op-side" id="op-side">
        <Sidebar
          variant="operator"
          header={<SidebarBrand />}
          footer={
            <div className="op-side__foot">
              {!view.canAct && (
                <div className="op-side__readonly">
                  <span className="op-chip">{t('operator.session.readOnly')}</span>
                  <OperatorKeyForm compact flash={view.flash} />
                </div>
              )}
              <SidebarPerson name={view.canAct && view.operator ? view.operator : t('operator.session.readOnly')} online={view.canAct} />
              <div className="op-side__session">
                <form method="post" action="/operador/salir">
                  <button type="submit" className="ui-btn ui-btn--ghost ui-btn--xs"><span>{t('operator.session.signOut')}</span></button>
                </form>
                <LanguageSwitcher />
              </div>
            </div>
          }
        >
          <SidebarSection>
            <SidebarRow as={Link} {...toQueue({})} label={t('operator.nav.allOpen')} active={plain} meta={<><NewCasesBadge />{count(counts?.allOpen)}</>} />
            <SidebarRow as={Link} {...toQueue({ vista: 'mias' })} label={t('operator.nav.mine')} active={onQueue && search.vista === 'mias'} meta={count(counts?.mine)} />
            <SidebarRow as={Link} {...toQueue({ vista: 'sin-asignar' })} label={t('operator.nav.unassigned')} active={onQueue && search.vista === 'sin-asignar'} meta={count(counts?.unassigned)} />
          </SidebarSection>
          <SidebarSection title={t('operator.nav.queues')}>
            {(counts?.queues ?? []).map((q) => (
              <SidebarRow key={q.name} as={Link} {...toQueue({ cola: q.name })} mono label={q.name} active={onQueue && search.cola === q.name} meta={String(q.count)} />
            ))}
          </SidebarSection>
          <SidebarSection title={t('operator.nav.records')}>
            <SidebarRow as={Link} to="/operador/monitoreo" label={t('operator.nav.monitor')} active={location.pathname.startsWith('/operador/monitoreo')} />
            <SidebarRow as={Link} to="/operador/trazas" label={t('operator.nav.traces')} active={location.pathname.startsWith('/operador/trazas')} />
          </SidebarSection>
        </Sidebar>
      </div>
      <NewCasesAnnouncer />
      <main className="op-main" id="contenido" tabIndex={-1}>
        {children}
      </main>
    </div>
  )
}
