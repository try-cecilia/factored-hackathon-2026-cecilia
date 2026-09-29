import { useEffect, useRef, type ComponentPropsWithoutRef, type ElementType, type KeyboardEvent, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Spinner } from '../Spinner'
import { useSidebar } from './SidebarContext'
import './SidebarRow.css'

export type SidebarDotTone = 'accent' | 'success' | 'caution' | 'danger'
export type SidebarRowStatus = 'working' | 'unread'

type OwnProps<C extends ElementType> = {
  /** What to render as: `'a'`, or the router's `Link` (`as={Link} to="/chat"`), so the kit does not depend on the router. Defaults to a button. */
  as?: C
  /** Name of the row. In the rail it is the accessible name and the tooltip. */
  label: string
  /** 16px icon. In the rail rows without one are left out. */
  icon?: ReactNode
  /** The current page or selection: fill, semibold text and `aria-current="page"`. */
  active?: boolean
  /** Second line, for case rows ("With a person · #4f21a9"). */
  description?: string
  /** Status dot before the text, for case rows. */
  dot?: SidebarDotTone
  /** Quiet text at the end: the age ("2h"), or the count in a queue. It is hidden while the row menu shows. */
  meta?: ReactNode
  /** Keyboard shortcut hint ("⌘N"), in mono. */
  shortcut?: string
  /** `working` shows a small spinner (the chat is still running); `unread` a dot and semibold text. Both are also read out. */
  status?: SidebarRowStatus
  /** Mono label, for queue names and ids. */
  mono?: boolean
  /** A `SidebarRowMenu`. Its trigger replaces the trailing content on hover and focus. */
  menu?: ReactNode
  /** The name is being edited: the row becomes a text field. Enter or leaving it calls `onRename`, Esc calls `onRenameCancel`. */
  renaming?: boolean
  onRename?: (name: string) => void
  onRenameCancel?: () => void
  /** Takes the focus when renaming starts. Only the dev gallery turns it off, to draw the state without moving the focus. */
  renameAutoFocus?: boolean
  /** Only for the dev gallery: draws a state without needing the pointer or the keyboard. */
  forceState?: 'hover' | 'focus'
  className?: string
}

export type SidebarRowProps<C extends ElementType = 'button'> = OwnProps<C> & Omit<ComponentPropsWithoutRef<C>, keyof OwnProps<C> | 'children'>

/** A row of the sidebar. The item (fill, radius, ring) wraps the link or button and the menu trigger, which cannot sit inside a link. */
export function SidebarRow<C extends ElementType = 'button'>({
  as,
  label,
  icon,
  active,
  description,
  dot,
  meta,
  shortcut,
  status,
  mono,
  menu,
  renaming,
  onRename,
  onRenameCancel,
  renameAutoFocus = true,
  forceState,
  className,
  ...rest
}: SidebarRowProps<C>) {
  const t = useT()
  const { variant, collapsed } = useSidebar()
  if (collapsed && !icon) return null

  const Tag: ElementType = as ?? 'button'
  const statusText = status ? t(`sidebar.status.${status}`) : undefined
  const classes = [
    'ui-sidebar__item',
    `ui-sidebar__item--${variant}`,
    collapsed && 'ui-sidebar__item--rail',
    description && 'ui-sidebar__item--two-line',
    menu && !collapsed && 'ui-sidebar__item--menu',
    renaming && 'ui-sidebar__item--renaming',
    mono && 'ui-sidebar__item--mono',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  if (renaming && !collapsed) {
    return (
      <li className={classes} data-state={forceState}>
        <RenameField initial={label} onRename={onRename} onCancel={onRenameCancel} autoFocus={renameAutoFocus} />
      </li>
    )
  }

  const trailing = !collapsed && (meta != null || shortcut || status || menu)
  return (
    <li className={classes} data-active={active ? '' : undefined} data-status={status} data-state={forceState}>
      <Tag
        type={Tag === 'button' ? 'button' : undefined}
        {...rest}
        className="ui-sidebar__row"
        aria-current={active ? 'page' : undefined}
        // In the rail there is no visible text, so the name (and the status) must not depend on it.
        aria-label={collapsed ? (statusText ? `${label}, ${statusText}` : label) : undefined}
      >
        {dot && !collapsed && <span className="ui-sidebar__dot" data-tone={dot} aria-hidden="true" />}
        {icon}
        {!collapsed && (
          <span className="ui-sidebar__text">
            <span className="ui-sidebar__label">{label}</span>
            {description && <span className="ui-sidebar__description">{description}</span>}
          </span>
        )}
        {trailing && (
          <span className="ui-sidebar__trail">
            {meta != null && <span className="ui-sidebar__meta">{meta}</span>}
            {shortcut && <span className="ui-sidebar__shortcut" aria-hidden="true">{shortcut}</span>}
            {status === 'working' && <Spinner size={12} tone="ink" />}
            {status === 'unread' && <span className="ui-sidebar__unread" aria-hidden="true" />}
            {statusText && !collapsed && <span className="ui-sidebar__sr">{statusText}</span>}
          </span>
        )}
        {collapsed && status && <span className="ui-sidebar__badge" data-status={status} aria-hidden="true" />}
        {collapsed && (
          <span className="ui-sidebar__tip" aria-hidden="true">
            {label}
            {shortcut && <span className="ui-sidebar__tip-key">{shortcut}</span>}
          </span>
        )}
      </Tag>
      {!collapsed && menu}
    </li>
  )
}

function RenameField({ initial, onRename, onCancel, autoFocus }: { initial: string; onRename?: (name: string) => void; onCancel?: () => void; autoFocus: boolean }) {
  const t = useT()
  const input = useRef<HTMLInputElement>(null)
  // Enter, Esc and blur can all fire for one edit; only the first counts.
  const settled = useRef(false)

  useEffect(() => {
    if (!autoFocus) return
    input.current?.focus()
    input.current?.select()
  }, [autoFocus])

  function settle(commit: boolean) {
    if (settled.current) return
    settled.current = true
    const name = input.current?.value.trim() ?? ''
    if (commit && name) onRename?.(name)
    else onCancel?.()
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      settle(true)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      settle(false)
    }
  }

  return (
    <input
      ref={input}
      className="ui-sidebar__rename"
      defaultValue={initial}
      aria-label={t('sidebar.row.rename')}
      spellCheck={false}
      onKeyDown={onKeyDown}
      onBlur={() => settle(true)}
    />
  )
}
