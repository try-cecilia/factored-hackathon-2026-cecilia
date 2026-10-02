import { useEffect, useRef, type RefObject } from 'react'

/**
 * A panel that slides over the page (the sidebar on a phone, the demo panel on a small screen): Escape closes it, the focus goes
 * into it when it opens and back to what opened it when it closes (unless the caller has already put it elsewhere on the page), and
 * Tab and Shift+Tab wrap inside it (the page behind is made `inert` by the caller; this keeps the focus from leaving the panel for
 * the browser's own controls).
 */
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]'

export function useDismiss(
  open: boolean,
  active: boolean,
  onClose: () => void,
  panel: RefObject<HTMLElement | null>,
  /** Where the focus goes back when what opened the panel cannot take it any more (a row of a drawer that closed as this opened). */
  fallback?: () => HTMLElement | null,
  /** Where the focus goes when it opens, instead of the first control (the demo panel's active scenario); it is brought into view. */
  initial?: () => HTMLElement | null,
) {
  const opener = useRef<Element | null>(null)
  const close = useRef(onClose)
  close.current = onClose
  const fallbackRef = useRef(fallback)
  fallbackRef.current = fallback
  const initialRef = useRef(initial)
  initialRef.current = initial

  useEffect(() => {
    if (!open || !active) return
    opener.current = document.activeElement
    const first = initialRef.current?.() ?? panel.current?.querySelector<HTMLElement>(FOCUSABLE)
    first?.focus()
    first?.scrollIntoView?.({ block: 'nearest' })
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') return close.current()
      if (event.key !== 'Tab' || !panel.current) return
      const stops = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.closest('[inert]') && el.tabIndex >= 0)
      if (stops.length === 0) return event.preventDefault()
      const at = stops.indexOf(document.activeElement as HTMLElement)
      // Focus put by hand on something that is not a stop (the demo panel's active card): Tab goes on to the next stop in the
      // document, Shift+Tab to the one before it, and the wrap is only for the ends.
      const here = document.activeElement
      if (at < 0 && here && here !== panel.current && panel.current.contains(here)) {
        const order = event.shiftKey ? Node.DOCUMENT_POSITION_PRECEDING : Node.DOCUMENT_POSITION_FOLLOWING
        const around = stops.filter((el) => here.compareDocumentPosition(el) & order)
        const target = event.shiftKey ? around[around.length - 1] : around[0]
        if (target) {
          event.preventDefault()
          return target.focus()
        }
      }
      const edge = event.shiftKey ? at <= 0 : at === stops.length - 1 || at < 0
      if (!edge) return
      event.preventDefault()
      stops[event.shiftKey ? stops.length - 1 : 0].focus()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      // Whoever closed the panel may already have put the focus somewhere on the page (the demo panel sends its message and focuses
      // the chat's input): that choice stays. Only a focus left in the panel, or lost, goes back to what opened it.
      const here = document.activeElement
      if (here instanceof HTMLElement && here !== document.body && document.contains(here) && !here.closest('[inert]') && !panel.current?.contains(here)) return
      const back = opener.current
      if (back instanceof HTMLElement && document.contains(back) && !back.closest('[inert]')) back.focus()
      else fallbackRef.current?.()?.focus()
    }
  }, [open, active, panel])
}
