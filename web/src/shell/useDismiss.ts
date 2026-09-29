import { useEffect, useRef, type RefObject } from 'react'

/**
 * A panel that slides over the page (the sidebar on a phone, the demo panel on a small screen): Escape closes it, the focus goes
 * into it when it opens and back to what opened it when it closes, and Tab and Shift+Tab wrap inside it (the page behind is made
 * `inert` by the caller; this keeps the focus from leaving the panel for the browser's own controls).
 */
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]'

export function useDismiss(
  open: boolean,
  active: boolean,
  onClose: () => void,
  panel: RefObject<HTMLElement | null>,
  /** Where the focus goes back when what opened the panel cannot take it any more (a row of a drawer that closed as this opened). */
  fallback?: () => HTMLElement | null,
) {
  const opener = useRef<Element | null>(null)
  const close = useRef(onClose)
  close.current = onClose
  const fallbackRef = useRef(fallback)
  fallbackRef.current = fallback

  useEffect(() => {
    if (!open || !active) return
    opener.current = document.activeElement
    const first = panel.current?.querySelector<HTMLElement>(FOCUSABLE)
    first?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') return close.current()
      if (event.key !== 'Tab' || !panel.current) return
      const stops = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.closest('[inert]') && el.tabIndex >= 0)
      if (stops.length === 0) return event.preventDefault()
      const at = stops.indexOf(document.activeElement as HTMLElement)
      const edge = event.shiftKey ? at <= 0 : at === stops.length - 1 || at < 0
      if (!edge) return
      event.preventDefault()
      stops[event.shiftKey ? stops.length - 1 : 0].focus()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      const back = opener.current
      if (back instanceof HTMLElement && document.contains(back) && !back.closest('[inert]')) back.focus()
      else fallbackRef.current?.()?.focus()
    }
  }, [open, active, panel])
}
