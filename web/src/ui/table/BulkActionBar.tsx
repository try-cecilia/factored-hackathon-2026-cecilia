import { useT } from '../../i18n/context'
import { Button, IconButton } from '../Button'
import './BulkActionBar.css'
import { CloseIcon } from './icons'

export type BulkAction = {
  id: string
  label: string
  onAction: () => void
  /** The main action of the bar: a lighter fill. Only one per bar. */
  primary?: boolean
  /** The least important action ("Release"): quieter text. */
  muted?: boolean
  disabled?: boolean
  loading?: boolean
}

type Props = {
  /** Number of selected rows. The bar is drawn only when it is above zero. */
  count: number
  actions: readonly BulkAction[]
  /** "Clear selection". */
  onClear: () => void
  className?: string
}

/**
 * Floating bar with what can be done to the selected rows. The count lives in a polite live region that stays in the
 * page even with no selection, so the first "1 selected" is announced too.
 */
export function BulkActionBar({ count, actions, onClear, className }: Props) {
  const t = useT()
  const text = count > 0 ? t(count === 1 ? 'table.bulk.selectedOne' : 'table.bulk.selectedMany', { count }) : ''
  return (
    <div className={className ? `ui-bulk-host ${className}` : 'ui-bulk-host'}>
      <p className="sr-only" aria-live="polite" aria-atomic="true">{text}</p>
      {count > 0 && (
        <div className="ui-bulk" role="group" aria-label={t('table.bulk.label')}>
          <span className="ui-bulk__count" aria-hidden="true">{text}</span>
          {actions.map((action) => (
            <Button
              key={action.id}
              variant="ghost"
              size="sm"
              tinted={action.primary}
              muted={action.muted}
              disabled={action.disabled}
              loading={action.loading}
              onClick={action.onAction}
            >
              {action.label}
            </Button>
          ))}
          <IconButton variant="ghost" size="sm" label={t('table.bulk.clear')} icon={<CloseIcon />} onClick={onClear} />
        </div>
      )}
    </div>
  )
}
