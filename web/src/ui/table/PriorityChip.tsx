import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import './PriorityChip.css'
import type { Priority, StatusTone } from './priority'

/** Ticket priority. Critical is the only solid chip; amber is Medium's tone and nothing else here. */
export function PriorityChip({ priority, children, className }: { priority: Priority; children?: ReactNode; className?: string }) {
  const t = useT()
  return (
    <span className={['ui-priority', `ui-priority--${priority}`, className].filter(Boolean).join(' ')}>
      {children ?? t(`table.priority.${priority}`)}
    </span>
  )
}

/** Dot plus label. The dot is decoration: the label carries the meaning, so color is never the only signal. */
export function StatusIndicator({ tone = 'neutral', children, className }: { tone?: StatusTone; children: ReactNode; className?: string }) {
  return (
    <span className={['ui-status', className].filter(Boolean).join(' ')}>
      <span className={`ui-status__dot ui-status__dot--${tone}`} aria-hidden="true" />
      {children}
    </span>
  )
}
