import { useEffect, useRef, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Spinner } from '../Spinner'
import { StatusBadge } from './Marks'
import './Toast.css'

export type ToastVariant = 'loading' | 'success' | 'error'

export type ToastProps = {
  variant?: ToastVariant
  /** The notice text, already in the customer's language. */
  children: ReactNode
  /** One optional action ("Retry"). It closes nothing by itself. */
  action?: { label: string; onClick: () => void }
  /** Draws the close button; it calls this. */
  onClose?: () => void
  /** Closes itself (calls `onClose`) after this many ms. The timer pauses while the pointer or focus is on the toast. */
  autoCloseMs?: number
  className?: string
}

/** A floating notice that never blocks the screen. Errors are `role="alert"`; the rest are polite status. */
export function Toast({ variant = 'success', children, action, onClose, autoCloseMs, className }: ToastProps) {
  const t = useT()
  const root = useRef<HTMLDivElement>(null)
  const paused = useRef(false)
  const closeRef = useRef(onClose)
  useEffect(() => {
    closeRef.current = onClose
  })

  useEffect(() => {
    if (!autoCloseMs) return
    let left = autoCloseMs
    let last = Date.now()
    const id = setInterval(() => {
      const now = Date.now()
      if (!paused.current) left -= now - last
      last = now
      if (left <= 0) {
        clearInterval(id)
        closeRef.current?.()
      }
    }, 200)
    return () => clearInterval(id)
  }, [autoCloseMs])

  const classes = ['ui-toast', `ui-toast--${variant}`, onClose && 'ui-toast--closable', className].filter(Boolean).join(' ')
  return (
    <div
      ref={root}
      className={classes}
      role={variant === 'error' ? 'alert' : 'status'}
      onPointerEnter={() => (paused.current = true)}
      onPointerLeave={() => (paused.current = root.current?.contains(document.activeElement) ?? false)}
      onFocus={() => (paused.current = true)}
      onBlur={() => (paused.current = false)}
    >
      {variant === 'loading' && <Spinner size={14} tone="onDark" />}
      {variant === 'success' && <StatusBadge kind="success" size={16} glyph={9} />}
      {variant === 'error' && <StatusBadge kind="danger" size={16} glyph={9} />}
      <span className="ui-toast__text">{children}</span>
      {action && (
        <button type="button" className="ui-toast__action" onClick={action.onClick}>
          {action.label}
        </button>
      )}
      {onClose && (
        <button type="button" className="ui-toast__close" onClick={onClose} aria-label={t('loaders.toast.close')}>
          <svg viewBox="0 0 20 20" width={12} height={12} aria-hidden="true" focusable="false">
            <path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
          </svg>
        </button>
      )}
    </div>
  )
}

/** The stack where toasts appear. Keep it mounted so screen readers already watch it when the first toast arrives. */
export function ToastRegion({ children, floating = true, label, className }: { children?: ReactNode; floating?: boolean; label?: string; className?: string }) {
  const t = useT()
  const classes = ['ui-toast-region', !floating && 'ui-toast-region--flow', className].filter(Boolean).join(' ')
  return (
    <div className={classes} role="region" aria-label={label ?? t('loaders.toast.region')} aria-live="polite" aria-relevant="additions text">
      {children}
    </div>
  )
}
