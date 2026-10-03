import { useId, useMemo, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { IconButton } from '../Button'
import { SidebarToggleIcon } from './icons'
import { SidebarProvider, useSidebar, type SidebarVariant } from './SidebarContext'
import './Sidebar.css'

export type SidebarProps = {
  /** `client` is the customer's chat sidebar (260px, 32px rows); `operator` is the compact desk one (220px, 26px rows, mono for queues and ids). */
  variant?: SidebarVariant
  /** Icon rail: only the icon of each row, with its name in a tooltip. Rows without an icon are left out. */
  collapsed?: boolean
  /** Asks the parent to collapse or expand. Without it there is no toggle. */
  onCollapsedChange?: (collapsed: boolean) => void
  /** Usually a `SidebarBrand`. */
  header?: ReactNode
  /** Usually a `SidebarPerson`. */
  footer?: ReactNode
  /** Rounded card (14px) for when the sidebar floats on its own, as in the state samples. Docked, it is flush with the page. */
  floating?: boolean
  /** Accessible name of the navigation. Defaults to a translated one per variant. */
  label?: string
  className?: string
  children: ReactNode
}

/** Tonal panel with no dividers: header, a scrolling navigation and a footer. Sections and rows go in as children. */
export function Sidebar({ variant = 'client', collapsed = false, onCollapsedChange, header, footer, floating, label, className, children }: SidebarProps) {
  const t = useT()
  const context = useMemo(
    () => ({ variant, collapsed, toggle: onCollapsedChange ? () => onCollapsedChange(!collapsed) : undefined }),
    [variant, collapsed, onCollapsedChange],
  )
  const classes = ['ui-sidebar', `ui-sidebar--${variant}`, collapsed && 'ui-sidebar--collapsed', floating && 'ui-sidebar--floating', className]
    .filter(Boolean)
    .join(' ')
  return (
    <SidebarProvider value={context}>
      <aside className={classes}>
        {header}
        <nav className="ui-sidebar__nav" aria-label={label ?? t(`sidebar.label.${variant}`)}>{children}</nav>
        {footer}
      </aside>
    </SidebarProvider>
  )
}

/** The product mascot on its sky tile (Paper keeps it). Nothing else in the sidebar is blue except the focus ring, the unread dot and the rename caret. Decorative: the wordmark next to it names the product. */
function Mascot({ size }: { size: number }) {
  return (
    <span className="ui-sidebar__mascot" style={{ width: size, height: size }} aria-hidden="true">
      <img src="/cecilia-avatar.png" alt="" width={18} height={18} draggable={false} />
    </span>
  )
}

/** Wordmark and mascot. In the client sidebar it carries the collapse toggle; in the rail the mascot expands it. */
/** The mascot and the wordmark; `product` names the side of the app next to it (the operator variant says "Operations" by default). */
export function SidebarBrand({ product }: { product?: string } = {}) {
  const t = useT()
  const { variant, collapsed, toggle } = useSidebar()

  if (collapsed) {
    return (
      <div className="ui-sidebar__brand">
        {toggle ? (
          <button type="button" className="ui-sidebar__brand-button" aria-label={t('sidebar.brand.expand')} aria-expanded={false} onClick={toggle}>
            <Mascot size={22} />
          </button>
        ) : (
          <Mascot size={22} />
        )}
      </div>
    )
  }

  return (
    <div className="ui-sidebar__brand">
      <Mascot size={variant === 'operator' ? 18 : 20} />
      <span className="ui-sidebar__wordmark">cecilai</span>
      {(product ?? (variant === 'operator' && t('sidebar.brand.operations'))) && <span className="ui-sidebar__product">{product ?? t('sidebar.brand.operations')}</span>}
      {toggle && (
        <IconButton
          variant="ghost"
          size="xs"
          className="ui-sidebar__toggle"
          label={t('sidebar.brand.collapse')}
          aria-expanded
          icon={<SidebarToggleIcon />}
          onClick={toggle}
        />
      )}
    </div>
  )
}

export type SidebarSectionProps = {
  /** Heading of the group ("Today", "Queues"). Left out, the group has no heading (the top actions). In the rail the heading is only read, not shown. */
  title?: string
  /** Quiet text at the end of the heading, e.g. "2 open". */
  meta?: string
  className?: string
  children: ReactNode
}

/** A group of rows under a heading. It is a list, so assistive tech announces how many rows it has. */
export function SidebarSection({ title, meta, className, children }: SidebarSectionProps) {
  const id = useId()
  return (
    <section className={className ? `ui-sidebar__section ${className}` : 'ui-sidebar__section'} aria-labelledby={title ? id : undefined}>
      {title && (
        <h2 className="ui-sidebar__heading" id={id}>
          <span className="ui-sidebar__heading-text">{title}</span>
          {meta && <span className="ui-sidebar__heading-meta">{meta}</span>}
        </h2>
      )}
      <ul className="ui-sidebar__list">{children}</ul>
    </section>
  )
}
