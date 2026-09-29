export type SortDirection = 'asc' | 'desc'
/** `null` is "no order": the rows come as the caller gave them. */
export type SortState = { key: string; direction: SortDirection } | null
export type AriaSort = 'ascending' | 'descending' | 'none'

/** Click on a header: none → asc → desc → none. A different column starts again at asc. */
export function nextSort(current: SortState, key: string): SortState {
  if (!current || current.key !== key) return { key, direction: 'asc' }
  if (current.direction === 'asc') return { key, direction: 'desc' }
  return null
}

export function directionOf(current: SortState, key: string): SortDirection | null {
  return current && current.key === key ? current.direction : null
}

export function ariaSort(current: SortState, key: string): AriaSort {
  const direction = directionOf(current, key)
  return direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none'
}

type SortValue = string | number | boolean | Date | null | undefined

/** Empty values go last in either direction; text compares by number-aware, accent-insensitive collation. */
export function compareValues(a: SortValue, b: SortValue, collator = defaultCollator): number {
  const aEmpty = a === null || a === undefined || a === ''
  const bEmpty = b === null || b === undefined || b === ''
  if (aEmpty || bEmpty) return aEmpty === bEmpty ? 0 : aEmpty ? 1 : -1
  if (typeof a === 'string' && typeof b === 'string') return collator.compare(a, b)
  const x = a instanceof Date ? a.getTime() : Number(a)
  const y = b instanceof Date ? b.getTime() : Number(b)
  return x < y ? -1 : x > y ? 1 : 0
}

const defaultCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** Client-side ordering for callers that hold every row. Stable; returns a new array and never touches the input. */
export function sortRows<Row>(rows: readonly Row[], sort: SortState, getValue: (row: Row, key: string) => SortValue): Row[] {
  if (!sort) return [...rows]
  const sign = sort.direction === 'asc' ? 1 : -1
  return rows
    .map((row, index) => ({ row, index, value: getValue(row, sort.key) }))
    .sort((a, b) => {
      const aEmpty = a.value === null || a.value === undefined || a.value === ''
      const bEmpty = b.value === null || b.value === undefined || b.value === ''
      // Empty values keep their place at the end whatever the direction.
      const order = aEmpty || bEmpty ? compareValues(a.value, b.value) : compareValues(a.value, b.value) * sign
      return order || a.index - b.index
    })
    .map((entry) => entry.row)
}
