import type { ReactNode } from 'react'

export type TableDensity = 'comfortable' | 'compact'

export type Column<Row> = {
  /** Stable key of the column. Sorting reports it back in `SortState.key`. */
  id: string
  /** Header text. Already translated by the caller. */
  header: string
  /** Content of the cell for one row. */
  cell: (row: Row, index: number) => ReactNode
  align?: 'start' | 'end'
  /** Fixed width (px number or CSS length). Without it the column takes the space that is left. */
  width?: number | string
  /** DM Mono, for ids, queues, ages and other codes. */
  mono?: boolean
  /** Semibold, for the name of the row and for amounts. */
  strong?: boolean
  /** Secondary text color (dates, queue names, locale). */
  muted?: boolean
  /** The header becomes a button that reports `onSortChange`. */
  sortable?: boolean
  /** Width of the placeholder bar while loading. Defaults to a varied width per row. */
  skeletonWidth?: number | string
  /** Draws the cell as `<th scope="row">`: the cell that names the row for assistive technology (usually the id or the subject). */
  rowHeader?: boolean
  /** Keep one line and cut with an ellipsis (long request text in the compact table). */
  truncate?: boolean
}

export type PaginationState = {
  /** 1-based. */
  page: number
  pageSize: number
  /** Rows across all pages. */
  total: number
  onPageChange: (page: number) => void
}
