import type { QueueRow } from '../../server/queue-row.ts'
import { isClosed } from './queue.ts'

/**
 * "Seen" is what the operator's own tab has already looked at, kept in `sessionStorage`: nothing about it reaches the API, it
 * ends with the tab, and a second tab starts from its own first look. It holds ticket ids and nothing else.
 */
export const SEEN_KEY = 'cecilai.operator.seen'

export type SeenStore = Pick<Storage, 'getItem' | 'setItem'>

/** The tab's own storage, or nothing when there is none (rendering on the server) or the browser denies it (reading it throws). */
export function browserStore(): SeenStore | undefined {
  try {
    return typeof sessionStorage === 'undefined' ? undefined : sessionStorage
  } catch {
    return undefined
  }
}

/** The ids of the last look, or null when there has been none (or the browser gives no storage: then this tab starts again from its baseline). */
export function readSeen(store: SeenStore | undefined): string[] | null {
  try {
    const parsed: unknown = JSON.parse(store?.getItem(SEEN_KEY) ?? 'null')
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : null
  } catch {
    return null
  }
}

export function writeSeen(store: SeenStore | undefined, ids: readonly string[]): void {
  try {
    store?.setItem(SEEN_KEY, JSON.stringify(ids))
  } catch {
    // A full or denied storage costs only the memory of what was seen after a reload; the console goes on.
  }
}

/**
 * The seen ids after the queue was read. With no earlier look (`null`) everything in the queue is the baseline, so opening the console
 * does not announce the whole backlog as news. Ids that left the list are dropped, which keeps the set as small as the queue.
 */
export function settle(seen: readonly string[] | null, rows: readonly QueueRow[]): string[] {
  const inQueue = new Set(rows.map((row) => row.ticket_id))
  return seen === null ? [...inQueue] : seen.filter((id) => inQueue.has(id))
}

export const addSeen = (seen: readonly string[], ids: readonly string[]): string[] => [...new Set([...seen, ...ids])]

/** The new cases: pending work (a case someone already decided is not news) that the operator has not looked at. */
export const unseenIds = (rows: readonly QueueRow[], seen: ReadonlySet<string>): string[] =>
  rows.filter((row) => !isClosed(row) && !seen.has(row.ticket_id)).map((row) => row.ticket_id)

const COUNT = /^\(\d+\)\s+/

/** A page title with the number of new cases in front: `(3) Cola · Cecilai`. */
export const withCount = (title: string, count: number): string => {
  const plain = title.replace(COUNT, '')
  return count > 0 ? `(${count}) ${plain}` : plain
}
