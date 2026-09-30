import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { getCase, getHistory, sendMessage } from '../server/chat.functions'
import { casesOf, deliveryOf, fromHistory, isOpenCase, mergeCases, splitCaseNews, type CaseRef, type Entry, type UserEntry } from './conversation'
import { newMessageKey } from './key'
import type { HistoryCase, HistoryResult, Reply } from './types'

/** How far a case is known: asked, failed to ask, not one of this session's (the API said 404), or answered. */
export type CaseState = { state: 'loading' } | { state: 'error' } | { state: 'not_found' } | { state: 'ready'; status: string; message: string | null }

/**
 * What one read of a case came to: `ended` is a session that is over, and the conversation says so; `superseded`, a read that
 * a newer one of the same case overtook (its answer was dropped: the newer one's is the one that counts).
 */
export type CaseRead = 'ready' | 'not_found' | 'error' | 'ended' | 'superseded'

export type CaseRow = { ref: CaseRef; state: CaseState }

export type Conversation = {
  /** The session the conversation below belongs to: it changes in the same render as the entries do, not before. */
  sessionRef: string
  entries: Entry[]
  /** A message is on its way: one turn at a time. */
  sending: boolean
  /** The session is over (the API said so): nothing more can be sent. */
  ended: boolean
  /** The conversation could not be read back when the page loaded. */
  historyFailed: boolean
  send: (text: string) => Promise<Reply | null>
  /** Sends a message that did not go through again, with the same key: a message that did arrive is not run twice. */
  retry: (id: number) => void
  /** Reads the conversation from the API again (what the message the API already has needs). */
  reload: () => Promise<void>
  cases: CaseRow[]
  refreshCases: () => void
  /** Reads one case again now (the case view's "update"); the sidebar and the handoff message follow. */
  refreshCase: (ticketId: string) => Promise<CaseRead>
}

const ConversationContext = createContext<Conversation | null>(null)

export function useConversation(): Conversation {
  const value = use(ConversationContext)
  if (!value) throw new Error('useConversation needs a ConversationProvider above it')
  return value
}

const CASE_POLL_MS = 45_000

/**
 * The conversation of one session, above the shell and the chat so the sidebar lists the cases the chat opens. It starts from
 * what the API kept (`initial`); another session (signing in again, a demo scenario) is another conversation, and starts over from
 * the `initial` of that session without remounting what is below (the demo panel keeps its steps).
 */
export function ConversationProvider({ sessionRef, initial, children }: { sessionRef: string; initial: HistoryResult; children: ReactNode }) {
  const [entries, setEntries] = useState<Entry[]>(() => (initial.ok ? fromHistory(initial.turns, 1, 0) : []))
  const [kept, setKept] = useState<HistoryCase[]>(() => (initial.ok ? initial.cases : []))
  const nextId = useRef(entries.length + 1)
  // Which session an answer was asked in, and how many times this conversation changed by hand since: an answer that comes back
  // for another session, or for a conversation that has moved on, is dropped instead of written over the present.
  const epoch = useRef(0)
  const edits = useRef(0)
  const [sending, setSending] = useState(false)
  const sendingRef = useRef(false)
  const [ended, setEnded] = useState(!initial.ok && initial.failure === 'session_expired')
  const [historyFailed, setHistoryFailed] = useState(!initial.ok && initial.failure === 'unavailable')
  const [states, setStates] = useState<Record<string, CaseState>>({})
  const statesRef = useRef(states)
  statesRef.current = states
  const asked = useRef(new Set<string>())
  // The last read asked for each case in this session: an answer to an older one that arrives later is stale.
  const reads = useRef(new Map<string, number>())

  const [current, setCurrent] = useState(sessionRef)
  if (current !== sessionRef) {
    setCurrent(sessionRef)
    setEntries(initial.ok ? fromHistory(initial.turns, 1, 0) : [])
    setKept(initial.ok ? initial.cases : [])
    setSending(false)
    setEnded(!initial.ok && initial.failure === 'session_expired')
    setHistoryFailed(!initial.ok && initial.failure === 'unavailable')
    setStates({})
  }
  // The bookkeeping that is not state follows in an effect: an answer that arrives for the session that was left is ignored.
  useEffect(() => {
    epoch.current += 1
    edits.current += 1
    nextId.current = (initial.ok ? fromHistory(initial.turns, 1, 0).length : 0) + 1
    sendingRef.current = false
    asked.current.clear()
    reads.current.clear()
  }, [sessionRef])

  const patch = useCallback((id: number, change: Partial<UserEntry>) => {
    setEntries((all) => all.map((e) => (e.id === id && e.role === 'user' ? { ...e, ...change } : e)))
  }, [])

  const loadCase = useCallback(async (ticketId: string): Promise<CaseRead> => {
    // The first look shows "loading"; the ones after keep the last answer on screen until the new one arrives, and a failed
    // one keeps it too (the caller is told it failed).
    const mine = epoch.current
    const read = (reads.current.get(ticketId) ?? 0) + 1
    reads.current.set(ticketId, read)
    const latest = () => mine === epoch.current && reads.current.get(ticketId) === read
    const failed = () => setStates((s) => (s[ticketId]?.state === 'ready' ? s : { ...s, [ticketId]: { state: 'error' } }))
    if (!(ticketId in statesRef.current)) setStates((s) => ({ ...s, [ticketId]: { state: 'loading' } }))
    try {
      const result = await getCase({ data: { ticket_id: ticketId } })
      if (!latest()) return 'superseded'
      if (result.ok) {
        setStates((s) => ({ ...s, [ticketId]: { state: 'ready', status: result.case.status, message: result.case.message } }))
        return 'ready'
      }
      if (result.failure === 'session_expired') {
        setEnded(true)
        return 'ended'
      }
      if (result.failure === 'not_found') {
        setStates((s) => ({ ...s, [ticketId]: { state: 'not_found' } }))
        return 'not_found'
      }
      failed()
      return 'error'
    } catch {
      if (!latest()) return 'superseded'
      failed()
      return 'error'
    }
  }, [])

  const entriesRef = useRef(entries)
  entriesRef.current = entries
  const keptRef = useRef(kept)
  keptRef.current = kept
  const refs = useMemo(() => mergeCases(kept, casesOf(entries)), [kept, entries])

  useEffect(() => {
    for (const { ticketId } of refs) {
      if (asked.current.has(ticketId)) continue
      asked.current.add(ticketId)
      void loadCase(ticketId)
    }
  }, [refs, loadCase])

  const refreshCases = useCallback(() => {
    for (const { ticketId } of mergeCases(keptRef.current, casesOf(entriesRef.current))) void loadCase(ticketId)
  }, [loadCase])

  // A case a person is working on changes without the customer doing anything: look again while the page is visible.
  useEffect(() => {
    if (ended) return
    const timer = setInterval(() => {
      if (document.visibilityState !== 'visible') return
      for (const { ticketId } of mergeCases(keptRef.current, casesOf(entriesRef.current))) {
        const known = statesRef.current[ticketId]
        if (!known || known.state === 'error' || (known.state === 'ready' && isOpenCase(known.status))) void loadCase(ticketId)
      }
    }, CASE_POLL_MS)
    return () => clearInterval(timer)
  }, [ended, loadCase])

  // One turn at a time: the ref answers a second click before React has re-rendered.
  const deliver = useCallback(async (id: number, text: string, key: string): Promise<Reply | null> => {
    if (sendingRef.current) return null
    sendingRef.current = true
    setSending(true)
    const mine = epoch.current
    edits.current += 1 // any send, a retry included, outdates the reloads already asked for
    patch(id, { delivery: 'sending', failure: undefined })
    try {
      const result = await sendMessage({ data: { message: text, key } })
      if (mine !== epoch.current) return null
      if (result.ok) {
        patch(id, { delivery: 'sent', failure: undefined })
        edits.current += 1
        setEntries((all) => [...all, { id: nextId.current++, role: 'assistant', reply: result.reply, at: Date.now(), to: id }])
        if (splitCaseNews(result.reply.response_text).news.length > 0) refreshCases()
        return result.reply
      }
      if (result.failure === 'session_expired') {
        setEnded(true)
        patch(id, { delivery: deliveryOf('ended'), failure: 'ended' })
      } else {
        patch(id, { delivery: deliveryOf(result.failure), failure: result.failure })
      }
    } catch {
      if (mine === epoch.current) patch(id, { delivery: 'uncertain', failure: 'unexpected' })
    } finally {
      if (mine === epoch.current) {
        sendingRef.current = false
        setSending(false)
      }
    }
    return null
  }, [patch, refreshCases])

  const send = useCallback((text: string) => {
    if (sendingRef.current) return Promise.resolve(null)
    const id = nextId.current++
    const key = newMessageKey()
    setEntries((all) => [...all, { id, role: 'user', text, at: Date.now(), key, delivery: 'sending' }])
    return deliver(id, text, key)
  }, [deliver])

  const retry = useCallback((id: number) => {
    const entry = entriesRef.current.find((e) => e.id === id)
    if (entry?.role !== 'user' || !entry.key) return
    void deliver(id, entry.text, entry.key)
  }, [deliver])

  const reload = useCallback(async () => {
    if (sendingRef.current) return
    const mine = { session: epoch.current, edits: edits.current }
    try {
      const result = await getHistory()
      if (mine.session !== epoch.current || mine.edits !== edits.current) return
      if (result.ok) {
        // A message the API said it already has but whose reply is not in what it kept stays, told so: reloading cannot show it.
        // One that did not go through (failed, or its answer got lost) stays too, with its key: a history that does not have it
        // yet does not show that it did not arrive, and sending it again with another key would be a second message.
        const said = new Set(result.turns.flatMap((t) => (t.role === 'user' ? [t.text] : [])))
        const gone = entriesRef.current.flatMap((e): Entry[] => {
          if (e.role !== 'user' || said.has(e.text)) return []
          if (e.failure === 'already_processed') return [{ ...e, failure: 'answer_gone' }]
          return e.key && (e.delivery === 'failed' || e.delivery === 'uncertain') ? [e] : []
        })
        const next = [...fromHistory(result.turns, nextId.current, Date.now()), ...gone]
        nextId.current += next.length + 1
        setKept(result.cases)
        edits.current += 1
        setEntries(next)
        setHistoryFailed(false)
      } else if (result.failure === 'session_expired') setEnded(true)
      else setHistoryFailed(true)
    } catch {
      if (mine.session === epoch.current && mine.edits === edits.current) setHistoryFailed(true)
    }
  }, [])

  const cases = useMemo<CaseRow[]>(() => refs.map((ref) => ({ ref, state: states[ref.ticketId] ?? { state: 'loading' } })), [refs, states])

  const value = useMemo<Conversation>(
    () => ({ sessionRef: current, entries, sending, ended, historyFailed, send, retry, reload, cases, refreshCases, refreshCase: loadCase }),
    [current, entries, sending, ended, historyFailed, send, retry, reload, cases, refreshCases, loadCase],
  )
  return <ConversationContext value={value}>{children}</ConversationContext>
}
