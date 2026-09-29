import type { ReactNode } from 'react'
import { AlertTriangleIcon } from './icons'
import './LimitedModeBanner.css'

export type LimitedModeBannerProps = {
  /** What still works and what does not. Already in the customer's language. */
  children: ReactNode
  className?: string
}

/** Degraded mode: the assistant is limited. Caution amber, announced politely as a status. */
export function LimitedModeBanner({ children, className }: LimitedModeBannerProps) {
  return (
    <div className={className ? `ui-limited ${className}` : 'ui-limited'} role="status">
      <AlertTriangleIcon />
      <p className="ui-limited__text">{children}</p>
    </div>
  )
}
