// Where the operator's keys are kept, with the rules for when a session ends. Plain code with an injectable clock so
// `node --test` can run it; operator-session.ts adds the cookie on top.
import { randomBytes } from 'node:crypto'

export const IDLE_MS = 30 * 60_000
export const ABSOLUTE_MS = 8 * 60 * 60_000
export const MAX_SESSIONS = 200
// Ids that were just consumed (replaced by a login or an elevation) are remembered briefly, only to tell a second request
// that arrives with the same cookie from a cookie that was never valid.
export const CONSUMED_MS = 5 * 60_000
export const MAX_CONSUMED = 1000

export type OperatorSession = {
  adminKey: string // reads: queue, tickets, monitoring (X-Admin-Key)
  operatorKey?: string // acts: claim, approve, reject, release (X-Operator-Key)
  operator?: string // the name the API gave that key
  createdAt: number
  lastSeen: number
}

export type Take = 'taken' | 'already' | 'none'

export type Lookup = { status: 'active'; session: OperatorSession } | { status: 'expired' } | { status: 'unknown' }

export class SessionStore {
  private sessions = new Map<string, OperatorSession>()
  private consumed = new Map<string, number>()
  private now: () => number
  private idleMs: number
  private absoluteMs: number

  constructor(now: () => number = Date.now, idleMs = IDLE_MS, absoluteMs = ABSOLUTE_MS) {
    this.now = now
    this.idleMs = idleMs
    this.absoluteMs = absoluteMs
  }

  private alive(session: OperatorSession, at: number) {
    return at - session.lastSeen < this.idleMs && at - session.createdAt < this.absoluteMs
  }

  start(adminKey: string, operatorKey?: string, operator?: string) {
    const at = this.now()
    for (const [id, session] of this.sessions) if (!this.alive(session, at)) this.sessions.delete(id)
    if (this.sessions.size >= MAX_SESSIONS) this.sessions.delete(this.sessions.keys().next().value!)
    const id = randomBytes(32).toString('base64url')
    this.sessions.set(id, { adminKey, operatorKey, operator, createdAt: at, lastSeen: at })
    return id
  }

  /**
   * `touch` says whether this look counts as the person being there. A click or an action does; the console's own
   * background refresh does not, or an abandoned tab would keep its session alive forever.
   */
  lookup(id: string | undefined, touch: boolean): Lookup {
    const session = id ? this.sessions.get(id) : undefined
    if (!id || !session) return { status: 'unknown' }
    const at = this.now()
    if (!this.alive(session, at)) {
      this.sessions.delete(id)
      return { status: 'expired' }
    }
    if (touch) session.lastSeen = at
    return { status: 'active', session }
  }

  private remember(id: string, at: number) {
    for (const [old, when] of this.consumed) if (at - when >= CONSUMED_MS) this.consumed.delete(old)
    if (this.consumed.size >= MAX_CONSUMED) this.consumed.delete(this.consumed.keys().next().value!)
    this.consumed.set(id, at)
  }

  /**
   * Consumes a session in one step, so of two requests that arrive with the same cookie only one gets 'taken' and the
   * other 'already'. 'none' is a cookie that never held (or no longer holds) a live session: nothing to replace.
   */
  take(id: string | undefined): Take {
    if (!id) return 'none'
    const at = this.now()
    const session = this.sessions.get(id)
    if (session) {
      this.sessions.delete(id)
      if (!this.alive(session, at)) return 'none'
      this.remember(id, at)
      return 'taken'
    }
    const when = this.consumed.get(id)
    if (when !== undefined && at - when < CONSUMED_MS) return 'already'
    this.consumed.delete(id)
    return 'none'
  }

  /**
   * The same session with an operator key added, under a new id; the old id stops working. Rights never grow under an id
   * that may already have been copied (fixation), and the 8-hour cap keeps counting from the original login.
   */
  elevate(id: string | undefined, operatorKey: string, operator?: string): string | null {
    const found = this.lookup(id, false)
    if (found.status !== 'active' || !id) return null
    this.take(id)
    const fresh = randomBytes(32).toString('base64url')
    this.sessions.set(fresh, { ...found.session, operatorKey, operator, lastSeen: this.now() })
    return fresh
  }

  end(id: string | undefined) {
    if (id) this.sessions.delete(id)
  }
}
