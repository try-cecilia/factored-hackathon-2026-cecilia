import './SortButton.css'
import { SortAscIcon, SortDescIcon } from './icons'
import type { SortDirection } from './sort'

type Props = {
  label: string
  /** `null` is unsorted: no arrow until the pointer or the keyboard is on the header. */
  direction: SortDirection | null
  onClick: () => void
  align?: 'start' | 'end'
  /** Only for the dev gallery: draws a state without needing the pointer or the keyboard. */
  forceState?: 'hover' | 'focus'
  className?: string
}

/** Header button of a sortable column. The state itself is announced by `aria-sort` on the `<th>` that holds it. */
export function SortButton({ label, direction, onClick, align = 'start', forceState, className }: Props) {
  const Arrow = direction === 'desc' ? SortDescIcon : SortAscIcon
  return (
    <button
      type="button"
      className={['ui-sort', align === 'end' && 'ui-sort--end', className].filter(Boolean).join(' ')}
      data-sort={direction ?? undefined}
      data-state={forceState}
      onClick={onClick}
    >
      <span>{label}</span>
      <Arrow className="ui-sort__arrow" strokeWidth={direction ? 2 : 1.8} />
    </button>
  )
}
