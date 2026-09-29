import { useEffect, useRef, type RefObject } from 'react'

/**
 * A panel that slides over the page (the sidebar on a phone, the demo panel on a small screen): Escape closes it, the focus goes
 * into it when it opens and back to what opened it when it closes.
 */
export function useDismiss(open: boolean, active: boolean, onClose: () => void, panel: RefObject<HTMLElement | null>) {
  const opener = useRef<Element | null>(null)
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    if (!open || !active) return
    opener.current = document.activeElement
    const first = panel.current?.querySelector<HTMLElement>('a[href], button:not([disabled]), input, [tabindex="0"]')
    first?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close.current()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      const back = opener.current
      if (back instanceof HTMLElement && document.contains(back)) back.focus()
    }
  }, [open, active, panel])
}
