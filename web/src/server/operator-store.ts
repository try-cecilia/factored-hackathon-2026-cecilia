// Where the operator's keys are kept, with the rules for when a session ends. Plain code with an injectable clock so
// `node --test` can run it; operator-session.ts adds the cookie on top.
import { randomBytes } from 'node:crypto'

export const IDLE_MS = 30 * 60_000
export const ABSOLUTE_MS = 8 * 60 * 60_000
export const MAX_SESSIONS = 200

export type OperatorSession = {
  adminKey: string // reads: queue, tickets, monitoring (X-Admin-Key)
  operatorKey?: string // acts: claim, approve, reject, release (X-Operator-Key)
  operator?: string // the name the API gave that key
  createdAt: number
  lastSeen: number
}

export type Lookup = { status: 'active'; session: OperatorSession } | { status: 'expired' } | { status: 'unknown' }

export class SessionStore {
  private sessions = new Map<string, OperatorSession>()
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

  end(id: string | undefined) {
    if (id) this.sessions.delete(id)
  }
}
