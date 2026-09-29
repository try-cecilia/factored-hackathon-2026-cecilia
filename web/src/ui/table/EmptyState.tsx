import type { ReactNode } from 'react'
import './EmptyState.css'

type Props = {
  title: string
  description?: string
  /** One way out, usually `<Button variant="ghost" tinted size="sm">`. */
  action?: ReactNode
  className?: string
}

/** No results: say why and offer one way out (Paper "UI · Data tables", block 6). */
export function EmptyState({ title, description, action, className }: Props) {
  return (
    <div className={className ? `ui-empty ${className}` : 'ui-empty'} role="status">
      <p className="ui-empty__title">{title}</p>
      {description && <p className="ui-empty__text">{description}</p>}
      {action}
    </div>
  )
}
