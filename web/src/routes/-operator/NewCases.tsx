import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Button } from '../../ui'
import type { QueueRow, Result } from '../../server/operator.functions'
import { addSeen, browserStore, readSeen, settle, unseenIds, withCount, writeSeen, type SeenStore } from './seen'

type NewCases = {
  /** The pending cases that arrived since the operator last looked. */
  ids: ReadonlySet<string>
  count: number
  /** Marks these as seen, or every new one when none are given. */
  markSeen: (ids?: readonly string[]) => void
}

const NONE: NewCases = { ids: new Set(), count: 0, markSeen: () => {} }
const Context = createContext<NewCases>(NONE)

export const useNewCases = () => useContext(Context)

/**
 * Which cases of the queue are new to this tab. The queue arrives by the console's own refresh; a case is new until the operator
 * opens it or asks to mark what is new as seen. The first read of a tab is its baseline, so nothing is new before the server
 * rendered page has hydrated (`seen` starts `null` and no count is shown until the browser has read its own storage).
 */
export function NewCasesProvider({ queue, store = browserStore, children }: { queue: Result<QueueRow[]>; store?: () => SeenStore | undefined; children: ReactNode }) {
  const remembered = useRef<string[] | null>(null)
  const [seen, setSeen] = useState<ReadonlySet<string> | null>(null)
  // A read that failed leaves the last good queue in place: the count must not drop to zero for a moment and come back.
  const latest = useRef<QueueRow[] | null>(null)
  if (queue.ok) latest.current = queue.data
  const rows = latest.current

  const commit = useCallback((next: string[]) => {
    remembered.current = next
    writeSeen(store(), next)
    setSeen(new Set(next))
  }, [store])

  // What this tab has seen, once there is a queue to take the baseline from. A child's effect (opening a case) runs before this
  // one on the first render, so it asks here instead of starting from an empty set, which would make the whole queue new.
  const current = useCallback(() => remembered.current ?? (latest.current ? settle(readSeen(store()), latest.current) : null), [store])

  useEffect(() => {
    if (rows) commit(settle(current(), rows))
  }, [rows, commit, current])

  const ids = useMemo(() => new Set(rows && seen ? unseenIds(rows, seen) : []), [rows, seen])
  const pending = useRef(ids)
  pending.current = ids
  // Stable, so a case that marks itself in an effect does not run again for every refresh.
  const markSeen = useCallback(
    (which?: readonly string[]) => {
      const base = current()
      const add = which ?? [...pending.current]
      if (base === null || add.every((id) => base.includes(id))) return
      commit(addSeen(base, add))
    },
    [commit, current],
  )
  const value = useMemo<NewCases>(() => ({ ids, count: ids.size, markSeen }), [ids, markSeen])

  useTabTitleCount(value.count)
  return <Context value={value}>{children}</Context>
}

/**
 * The count in front of the tab's title, on every page of the console. The router writes the title of each page, so the count is put
 * back when it does; and it comes off when the console goes (the customer's pages must not inherit it).
 */
function useTabTitleCount(count: number) {
  useEffect(() => {
    const apply = () => {
      const next = withCount(document.title, count)
      if (next !== document.title) document.title = next
    }
    apply()
    const observer = new MutationObserver(apply)
    observer.observe(document.head, { childList: true, characterData: true, subtree: true })
    return () => {
      observer.disconnect()
      document.title = withCount(document.title, 0)
    }
  }, [count])
}

const phrase = (t: ReturnType<typeof useT>, count: number) => (count === 1 ? t('operator.new.one') : t('operator.new.other', { count }))

/**
 * The polite announcement, for screen readers only: a live region that is always in the page (one that appears with its text is
 * often not read), never moving the focus. It speaks when the count goes up, not when it goes down, and clears at zero.
 */
export function NewCasesAnnouncer() {
  const t = useT()
  const { count } = useNewCases()
  const [spoken, setSpoken] = useState(0)
  const [last, setLast] = useState(0)
  if (count !== last) {
    setLast(count)
    if (count === 0) setSpoken(0)
    else if (count > last) setSpoken(count)
  }
  return <div className="sr-only" role="status" aria-live="polite">{spoken > 0 ? phrase(t, spoken) : ''}</div>
}

/** The number of new cases beside an entry of the sidebar, with its words for assistive technology. Nothing when there are none. */
export function NewCasesBadge() {
  const t = useT()
  const { count } = useNewCases()
  if (count === 0) return null
  return (
    <>
      <span className="op-new-count" aria-hidden="true">+{count}</span>
      <span className="sr-only">{phrase(t, count)}</span>
    </>
  )
}

/** The mark of a new case in the queue row: a dot, and the word for who cannot see it. */
export function NewMark({ id }: { id: string }) {
  const t = useT()
  const { ids } = useNewCases()
  if (!ids.has(id)) return null
  return (
    <>
      <span className="op-new-dot" aria-hidden="true" />
      <span className="sr-only">{t('operator.new.row')}</span>
    </>
  )
}

/** What the queue's header says while there are new cases, and the one way to be done with it. Not live: the announcement is the announcer's. */
export function NewCasesBar() {
  const t = useT()
  const { count, markSeen } = useNewCases()
  if (count === 0) return null
  return (
    <p className="op-newbar">
      <span>{phrase(t, count)}</span>
      <Button variant="ghost" tinted size="xs" onClick={() => markSeen()}>{t('operator.new.markSeen')}</Button>
    </p>
  )
}
