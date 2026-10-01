import { createContext, useCallback, useContext, useId, useMemo, useState, type ReactNode } from 'react'
import { useT } from '../../i18n/context'

type Folds = { isOpen: (id: string) => boolean; toggle: (id: string) => void }

const FoldsContext = createContext<Folds | null>(null)

/**
 * The sections of the drawer that fold. Which are open lives here, not in each section, so a section that is drawn again (the
 * customer's context arriving, or read again) keeps what the operator opened. Everything starts closed; the panel is keyed by
 * ticket, so a new ticket starts closed again.
 */
export function FoldGroup({ children }: { children: ReactNode }) {
  const t = useT()
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())
  const toggle = useCallback((id: string) => setOpen((now) => {
    const next = new Set(now)
    if (!next.delete(id)) next.add(id)
    return next
  }), [])
  const value = useMemo<Folds>(() => ({ isOpen: (id) => open.has(id), toggle }), [open, toggle])
  return (
    <FoldsContext.Provider value={value}>
      <section className="op-sheet op-folds" aria-label={t('operator.ticket.sections.label')}>{children}</section>
    </FoldsContext.Provider>
  )
}

type FoldProps = {
  /** Stable name of the section: what the group remembers it by. */
  id: string
  title: string
  /** What the closed section says about itself, at its right. A chip (`tone="alert"`) when something in it needs a look. */
  summary: ReactNode
  tone?: 'alert'
  /** A section with nothing in it is drawn quiet and does not open. */
  empty?: boolean
  children?: ReactNode
}

export function Fold({ id, title, summary, tone, empty, children }: FoldProps) {
  const folds = useContext(FoldsContext)
  const bodyId = useId()
  const open = !empty && !!folds?.isOpen(id)
  const head = (
    <>
      <svg className="op-fold__chevron" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" focusable="false">
        <path d="M4.5 3l3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="op-fold__title">{title}</span>
      <span className={tone === 'alert' ? 'op-fold__summary op-fold__summary--alert' : 'op-fold__summary'}>{summary}</span>
    </>
  )
  return (
    <div className="op-fold" data-open={open ? '' : undefined} data-empty={empty ? '' : undefined}>
      {empty ? (
        <div className="op-fold__head">{head}</div>
      ) : (
        <h3 className="op-fold__heading">
          <button type="button" className="op-fold__head" aria-expanded={open} aria-controls={bodyId} onClick={() => folds?.toggle(id)}>{head}</button>
        </h3>
      )}
      {open && <div id={bodyId} className="op-fold__body">{children}</div>}
    </div>
  )
}
