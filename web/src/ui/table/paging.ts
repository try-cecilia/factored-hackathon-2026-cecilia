export type PageItem = number | 'start-ellipsis' | 'end-ellipsis'

export const MAX_PAGES_WITHOUT_ELLIPSIS = 7

/** Pages are 1-based. Zero rows still count as one (empty) page. */
export function pageCount(total: number, pageSize: number): number {
  if (!(pageSize > 0)) return 1
  return Math.max(1, Math.ceil(Math.max(0, total) / pageSize))
}

/** Keeps a page inside 1..pageCount; non-numbers fall back to the first page. */
export function clampPage(page: number, total: number, pageSize: number): number {
  const last = pageCount(total, pageSize)
  if (!Number.isFinite(page)) return 1
  return Math.min(Math.max(1, Math.trunc(page)), last)
}

/** "1–25 of 138": both ends 1-based and inclusive. With no rows it is 0–0. */
export function pageRange(page: number, total: number, pageSize: number): { from: number; to: number } {
  const rows = Math.max(0, Math.trunc(total))
  if (rows === 0) return { from: 0, to: 0 }
  const current = clampPage(page, rows, pageSize)
  const from = (current - 1) * pageSize + 1
  return { from, to: Math.min(current * pageSize, rows) }
}

/**
 * Numbers to draw in the footer: first, last and a window around the current one, with an ellipsis where pages
 * are skipped. An ellipsis never stands for a single page (that page is drawn instead).
 */
export function pageItems(page: number, count: number): PageItem[] {
  const last = Math.max(1, Math.trunc(count))
  const current = Math.min(Math.max(1, Math.trunc(page)), last)
  if (last <= MAX_PAGES_WITHOUT_ELLIPSIS) return Array.from({ length: last }, (_, i) => i + 1)

  let start: number
  let end: number
  if (current <= 4) [start, end] = [2, 5]
  else if (current >= last - 3) [start, end] = [last - 4, last - 1]
  else [start, end] = [current - 1, current + 1]

  const items: PageItem[] = [1]
  if (start > 2) items.push('start-ellipsis')
  for (let n = start; n <= end; n++) items.push(n)
  if (end < last - 1) items.push('end-ellipsis')
  items.push(last)
  return items
}

export function hasPrevious(page: number): boolean {
  return page > 1
}

export function hasNext(page: number, total: number, pageSize: number): boolean {
  return page < pageCount(total, pageSize)
}
