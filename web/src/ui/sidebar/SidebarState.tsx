import type { ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Skeleton } from '../loaders/Skeleton'
import './SidebarState.css'

export type SidebarEmptyProps = {
  /** Defaults to a translated "No chats yet". */
  title?: string
  description?: string
  /** The way out, usually a small primary `Button` ("New chat"). */
  action?: ReactNode
  className?: string
}

/** Empty state of the chat list: what is missing, what to do, one action. On its own it is a tonal card; inside a `Sidebar` it takes the panel's fill. */
export function SidebarEmpty({ title, description, action, className }: SidebarEmptyProps) {
  const t = useT()
  return (
    <div className={className ? `ui-sidebar__empty ${className}` : 'ui-sidebar__empty'}>
      <p className="ui-sidebar__empty-title">{title ?? t('sidebar.empty.title')}</p>
      <p className="ui-sidebar__empty-text">{description ?? t('sidebar.empty.description')}</p>
      {action}
    </div>
  )
}

// Widths of Paper's placeholder lines, as [width, height, extra space above]: a heading, three rows, another heading, two rows.
const lines: readonly (readonly [number, number, number?])[] = [
  [48, 10],
  [190, 12],
  [150, 12],
  [170, 12],
  [64, 10, 6],
  [180, 12],
  [120, 12],
]

/** Loading state of the chat list: placeholder headings and rows, announced once as "Loading" instead of line by line. */
export function SidebarSkeleton({ className }: { className?: string }) {
  const t = useT()
  return (
    <div className={className ? `ui-sidebar__skeleton ${className}` : 'ui-sidebar__skeleton'} role="status" aria-busy="true" aria-label={t('sidebar.loading')}>
      {lines.map(([width, height, gap], index) => (
        <Skeleton key={index} width={width} height={height} radius="var(--radius-pill)" style={{ maxWidth: '100%', marginTop: gap }} />
      ))}
    </div>
  )
}
