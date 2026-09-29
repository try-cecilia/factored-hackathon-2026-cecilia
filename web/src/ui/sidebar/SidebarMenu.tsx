import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode, type Ref } from 'react'
import { createPortal } from 'react-dom'
import { useT } from '../../i18n/context'
import { SidebarArchiveIcon, SidebarDeleteIcon, SidebarMoreIcon, SidebarPinIcon, SidebarRenameIcon } from './icons'
import { matchTypeahead, moveFocus, nextTypeahead, type MenuNavKey } from './menu-nav'
import { placeMenu } from './placement'
import './SidebarMenu.css'

export type SidebarMenuItem = {
  id: string
  label: string
  icon?: ReactNode
  /** Destructive action: danger color. */
  danger?: boolean
  disabled?: boolean
  /** Leaves extra space above, to set an action apart (Delete) with space instead of a line. */
  separated?: boolean
}

export type SidebarMenuProps = {
  /** Accessible name of the menu. */
  label: string
  items: readonly SidebarMenuItem[]
  onSelect: (id: string) => void
  /** Esc closes and Tab leaves; the owner decides where the focus goes. */
  onClose?: (reason: 'escape' | 'tab') => void
  /** Which item takes the focus when the menu mounts. `false` leaves the focus alone, for a menu drawn on the page. */
  autoFocus?: 'first' | 'last' | false
  /** Only for the dev gallery: highlights an item without needing the keyboard. */
  forceActive?: number
  className?: string
  style?: CSSProperties
  menuRef?: Ref<HTMLDivElement>
}

const navKeys = new Set<string>(['ArrowDown', 'ArrowUp', 'Home', 'End'])

/** The floating layer of a row menu: soft shadow, `role="menu"`, arrows, Home/End and type-ahead. Items are focused one at a time (roving tabindex). */
export function SidebarMenu({ label, items, onSelect, onClose, autoFocus = 'first', forceActive, className, style, menuRef }: SidebarMenuProps) {
  const enabled = useMemo(() => items.map((item) => !item.disabled), [items])
  const [active, setActive] = useState(() =>
    autoFocus ? moveFocus(enabled, -1, autoFocus === 'last' ? 'ArrowUp' : 'ArrowDown') : (forceActive ?? -1),
  )
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const typed = useRef({ buffer: '', at: 0 })
  const focusable = autoFocus !== false

  useEffect(() => {
    if (focusable && active >= 0) refs.current[active]?.focus({ preventScroll: true })
  }, [active, focusable])

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (navKeys.has(event.key)) {
      event.preventDefault()
      setActive(moveFocus(enabled, active, event.key as MenuNavKey))
    } else if (event.key === 'Escape') {
      event.preventDefault()
      onClose?.('escape')
    } else if (event.key === 'Tab') {
      event.preventDefault()
      onClose?.('tab')
    } else if (!event.ctrlKey && !event.metaKey && !event.altKey) {
      const now = Date.now()
      const buffer = nextTypeahead(typed.current.buffer, event.key, now - typed.current.at)
      if (buffer === null) return
      typed.current = { buffer, at: now }
      const match = matchTypeahead(items.map((item) => item.label), enabled, active, buffer)
      if (match >= 0) setActive(match)
    }
  }

  // Exactly one item is in the tab order: the active one, or the first enabled while none is.
  const tabStop = active >= 0 ? active : enabled.indexOf(true)

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label={label}
      className={className ? `ui-sidebar-menu ${className}` : 'ui-sidebar-menu'}
      style={style}
      onKeyDown={focusable ? onKeyDown : undefined}
    >
      {items.map((item, index) => (
        <button
          key={item.id}
          ref={(node) => {
            refs.current[index] = node
          }}
          type="button"
          role="menuitem"
          className="ui-sidebar-menu__item"
          data-danger={item.danger ? '' : undefined}
          data-separated={item.separated ? '' : undefined}
          data-active={index === (focusable ? undefined : forceActive) ? '' : undefined}
          aria-disabled={item.disabled || undefined}
          tabIndex={focusable && index === tabStop ? 0 : -1}
          onMouseEnter={focusable && !item.disabled ? () => setActive(index) : undefined}
          onClick={item.disabled ? undefined : () => onSelect(item.id)}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  )
}

/** Rename, Pin, Archive, Delete: the actions of a chat row, translated. Delete is set apart. */
export function useChatMenuItems(): SidebarMenuItem[] {
  const t = useT()
  return useMemo(
    () => [
      { id: 'rename', label: t('sidebar.menu.rename'), icon: <SidebarRenameIcon /> },
      { id: 'pin', label: t('sidebar.menu.pin'), icon: <SidebarPinIcon /> },
      { id: 'archive', label: t('sidebar.menu.archive'), icon: <SidebarArchiveIcon /> },
      { id: 'delete', label: t('sidebar.menu.delete'), icon: <SidebarDeleteIcon />, danger: true, separated: true },
    ],
    [t],
  )
}

export type SidebarRowMenuProps = {
  /** Name of the row the menu belongs to; it names the trigger and the menu ("Options for {name}"). */
  name: string
  items: readonly SidebarMenuItem[]
  onSelect: (id: string) => void
}

/** The "···" trigger of a row and its floating menu. Pass it as the `menu` of a `SidebarRow`. The layer goes to `document.body`, so the scrolling sidebar cannot clip it. */
export function SidebarRowMenu({ name, items, onSelect }: SidebarRowMenuProps) {
  const t = useT()
  const trigger = useRef<HTMLButtonElement>(null)
  const layer = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState<false | 'first' | 'last'>(false)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)
  const title = t('sidebar.row.options', { name })

  function close(refocus: boolean) {
    setOpen(false)
    setPosition(null)
    if (refocus) trigger.current?.focus()
  }

  // Measure after the first paint of the hidden layer, then show it in place.
  useLayoutEffect(() => {
    if (!open || !trigger.current || !layer.current) return
    const anchor = trigger.current.getBoundingClientRect()
    const size = layer.current.getBoundingClientRect()
    const { left, top } = placeMenu(anchor, size, { width: window.innerWidth, height: window.innerHeight })
    setPosition({ left, top })
  }, [open])

  useEffect(() => {
    if (!open) return
    const outside = (event: Event) => {
      const target = event.target as Node
      if (!layer.current?.contains(target) && !trigger.current?.contains(target)) close(false)
    }
    // The layer is placed once, so anything that moves the trigger closes it.
    const scroll = (event: Event) => {
      if (!layer.current?.contains(event.target as Node)) close(false)
    }
    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('scroll', scroll, true)
    const resize = () => close(false)
    window.addEventListener('resize', resize)
    return () => {
      document.removeEventListener('pointerdown', outside, true)
      document.removeEventListener('scroll', scroll, true)
      window.removeEventListener('resize', resize)
    }
  }, [open])

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="ui-sidebar__menu-trigger"
        aria-label={title}
        aria-haspopup="menu"
        aria-expanded={open !== false}
        onClick={() => (open ? close(true) : setOpen('first'))}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            setOpen(event.key === 'ArrowDown' ? 'first' : 'last')
          }
        }}
      >
        <SidebarMoreIcon />
      </button>
      {open &&
        createPortal(
          <SidebarMenu
            menuRef={layer}
            label={title}
            items={items}
            autoFocus={open}
            className="ui-sidebar-menu--layer"
            // Invisible but focusable until measured, so the first item can take the focus right away.
            style={position ? { left: position.left, top: position.top } : { left: 0, top: 0, opacity: 0, pointerEvents: 'none' }}
            onClose={() => close(true)}
            onSelect={(id) => {
              close(true)
              // After returning the focus, so an action that moves it (rename) has the last word.
              onSelect(id)
            }}
          />,
          document.body,
        )}
    </>
  )
}
