import type { KeyboardEvent, MouseEvent, ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Skeleton } from '../loaders/Skeleton'
import { BulkActionBar, type BulkAction } from './BulkActionBar'
import './DataTable.css'
import { EmptyState } from './EmptyState'
import { Pagination } from './Pagination'
import { RowCheckbox } from './RowCheckbox'
import { selectAllState, toggleAll, toggleId } from './selection'
import { SortButton } from './SortButton'
import { ariaSort, directionOf, nextSort, type SortState } from './sort'
import type { Column, PaginationState, TableDensity } from './types'

export type DataTableEmpty = { title: string; description?: string; action?: ReactNode }

export type DataTableProps<Row> = {
  rows: readonly Row[]
  columns: readonly Column<Row>[]
  getRowId: (row: Row) => string
  /** Accessible name of the table. It is not drawn: the page around it already shows the title. */
  caption: string
  /** comfortable: 48px rows (customer). compact: 32px rows, 12px text (operator). */
  density?: TableDensity
  /** Controlled order. Only columns with `sortable` react to it, and only when `onSortChange` is given. */
  sort?: SortState
  onSortChange?: (sort: SortState) => void
  /** Controlled selection. The checkbox column appears when both `selectedIds` and `onSelectionChange` are given. */
  selectedIds?: readonly string[]
  onSelectionChange?: (ids: string[]) => void
  /** Accessible name of a row's checkbox ("Select 4f21a9"). Without it, "Select row". */
  getRowLabel?: (row: Row) => string
  /** Actions of the bulk bar, drawn while something is selected. */
  bulkActions?: readonly BulkAction[]
  /** Makes rows interactive: focusable, with Enter and Space. Leave it out when the row does nothing. */
  onRowClick?: (row: Row) => void
  /** The row whose detail is open next to the table: drawn with the selected fill and marked `aria-current`. It is not a selection. */
  activeRowId?: string
  loading?: boolean
  /** Placeholder rows while loading. */
  skeletonRows?: number
  /** Drawn instead of the table when there are no rows. */
  empty?: DataTableEmpty
  pagination?: PaginationState
  className?: string
  /** Only for the dev gallery: draws the hover fill on a row without the pointer. */
  forceHoverId?: string
}

// Varied bar widths so the placeholder rows do not look like a barcode (Paper block 5).
const SKELETON_WIDTHS = [60, 150, 110, 64, 170, 130]
const INTERACTIVE = 'a, button, input, select, textarea, label, [role="button"]'

export function DataTable<Row>({
  rows,
  columns,
  getRowId,
  caption,
  density = 'comfortable',
  sort = null,
  onSortChange,
  selectedIds,
  onSelectionChange,
  getRowLabel,
  bulkActions = [],
  onRowClick,
  activeRowId,
  loading = false,
  skeletonRows = 4,
  empty,
  pagination,
  className,
  forceHoverId,
}: DataTableProps<Row>) {
  const t = useT()
  const selectable = selectedIds !== undefined && onSelectionChange !== undefined
  const selected = selectedIds ?? []
  const visibleIds = rows.map(getRowId)
  const allState = selectAllState(visibleIds, selected)
  const showEmpty = !loading && rows.length === 0 && empty !== undefined

  function onRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, row: Row) {
    if (event.target !== event.currentTarget) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onRowClick?.(row)
    }
  }

  function onRowActivate(event: MouseEvent<HTMLTableRowElement>, row: Row) {
    // A click on a control inside the row (checkbox, link, menu button) is for that control.
    if ((event.target as HTMLElement).closest(INTERACTIVE)) return
    onRowClick?.(row)
  }

  return (
    <div className={['ui-dt', `ui-dt--${density}`, className].filter(Boolean).join(' ')}>
      <p className="sr-only" role="status">{loading ? t('table.loading') : ''}</p>

      {showEmpty ? (
        <EmptyState title={empty.title} description={empty.description} action={empty.action} />
      ) : (
        <table className="ui-dt__table" aria-busy={loading || undefined}>
          <caption className="sr-only">{caption}</caption>
          <colgroup>
            {selectable && <col className="ui-dt__col-check" />}
            {columns.map((column) => (
              <col key={column.id} style={column.width !== undefined ? { width: column.width } : undefined} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {selectable && (
                <th scope="col" className="ui-dt__check">
                  <RowCheckbox
                    label={t('table.select.all')}
                    checked={allState === 'all'}
                    indeterminate={allState === 'some'}
                    disabled={loading || rows.length === 0}
                    onChange={() => onSelectionChange(toggleAll(visibleIds, selected))}
                  />
                </th>
              )}
              {columns.map((column) => {
                const sortable = column.sortable && onSortChange !== undefined
                return (
                  <th
                    key={column.id}
                    scope="col"
                    className={column.align === 'end' ? 'ui-dt__th ui-dt__th--end' : 'ui-dt__th'}
                    aria-sort={sortable ? ariaSort(sort, column.id) : undefined}
                  >
                    {sortable ? (
                      <SortButton
                        label={column.header}
                        direction={directionOf(sort, column.id)}
                        align={column.align}
                        onClick={() => onSortChange(nextSort(sort, column.id))}
                      />
                    ) : (
                      column.header
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: skeletonRows }, (_, rowIndex) => (
                  <tr key={rowIndex} className="ui-dt__row ui-dt__row--skeleton" aria-hidden="true">
                    {selectable && <td className="ui-dt__check" />}
                    {columns.map((column, columnIndex) => (
                      <td key={column.id} className={column.align === 'end' ? 'ui-dt__cell ui-dt__cell--end' : 'ui-dt__cell'}>
                        <Skeleton
                          width={column.skeletonWidth ?? SKELETON_WIDTHS[(rowIndex + columnIndex * 2) % SKELETON_WIDTHS.length]}
                          height={10}
                          radius="var(--radius-pill)"
                          style={{ maxWidth: '100%' }}
                          className="ui-dt__bar"
                        />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.map((row, index) => {
                  const id = getRowId(row)
                  const isSelected = selected.includes(id)
                  const isActive = activeRowId === id
                  return (
                    <tr
                      key={id}
                      className={onRowClick ? 'ui-dt__row ui-dt__row--action' : 'ui-dt__row'}
                      data-selected={isSelected || isActive ? '' : undefined}
                      aria-current={isActive ? 'true' : undefined}
                      data-state={forceHoverId === id ? 'hover' : undefined}
                      tabIndex={onRowClick ? 0 : undefined}
                      onClick={onRowClick ? (event) => onRowActivate(event, row) : undefined}
                      onKeyDown={onRowClick ? (event) => onRowKeyDown(event, row) : undefined}
                    >
                      {selectable && (
                        <td className="ui-dt__check">
                          <RowCheckbox
                            label={getRowLabel ? t('table.select.rowNamed', { name: getRowLabel(row) }) : t('table.select.row')}
                            checked={isSelected}
                            onChange={() => onSelectionChange(toggleId(selected, id))}
                          />
                        </td>
                      )}
                      {columns.map((column) => {
                        const Cell = column.rowHeader ? 'th' : 'td'
                        return (
                          <Cell
                            key={column.id}
                            scope={column.rowHeader ? 'row' : undefined}
                            className={cellClass(column)}
                          >
                            {column.cell(row, index)}
                          </Cell>
                        )
                      })}
                    </tr>
                  )
                })}
          </tbody>
        </table>
      )}

      {pagination && pagination.total > 0 && (
        <Pagination
          className="ui-dt__pager"
          page={pagination.page}
          pageSize={pagination.pageSize}
          total={pagination.total}
          onPageChange={pagination.onPageChange}
        />
      )}

      {selectable && (
        <BulkActionBar
          className="ui-dt__bulk"
          count={selected.length}
          actions={bulkActions}
          onClear={() => onSelectionChange([])}
        />
      )}
    </div>
  )
}

function cellClass<Row>(column: Column<Row>) {
  return [
    'ui-dt__cell',
    column.align === 'end' && 'ui-dt__cell--end',
    column.mono && 'ui-dt__cell--mono',
    column.strong && 'ui-dt__cell--strong',
    column.muted && 'ui-dt__cell--muted',
    column.truncate && 'ui-dt__cell--truncate',
  ]
    .filter(Boolean)
    .join(' ')
}

/** Name of the row with its round mark (28px, the first letter): the "merchant" cell of the comfortable table. */
export function RowIdentity({ mark, children }: { mark: string; children: ReactNode }) {
  return (
    <span className="ui-dt__identity">
      <span className="ui-dt__mark" aria-hidden="true">{mark}</span>
      <span className="ui-dt__name">{children}</span>
    </span>
  )
}
