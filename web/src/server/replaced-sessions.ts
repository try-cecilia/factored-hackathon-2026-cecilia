import { createHash } from 'node:crypto'

/**
 * The session tokens a login has replaced in the browser that held them, for a while. The explicit sign-out waits on the API before it
 * answers, and a login from the same browser (another tab) may finish meanwhile and set a new cookie: the sign-out asks here before
 * it sends a deletion that, arriving after that Set-Cookie, would take the new cookie. One process, like the sessions themselves
 * (LIMITATIONS.md). It holds a digest, never the token, and a bounded number of them.
 */
export class ReplacedSessions {
  #until = new Map<string, number>()
  readonly #now: () => number
  readonly #ttlMs: number
  readonly #max: number

  constructor(now: () => number = Date.now, ttlMs = 120_000, max = 1_000) {
    this.#now = now
    this.#ttlMs = ttlMs
    this.#max = max
  }

  #key = (token: string) => createHash('sha256').update(token).digest('hex')

  #prune() {
    const now = this.#now()
    for (const [key, until] of this.#until) if (until <= now) this.#until.delete(key)
    // The oldest go first when there are too many; a Map keeps its insertion order.
    for (const key of this.#until.keys()) {
      if (this.#until.size <= this.#max) break
      this.#until.delete(key)
    }
  }

  note(token: string | undefined) {
    if (!token) return
    const key = this.#key(token)
    this.#until.delete(key)
    this.#until.set(key, this.#now() + this.#ttlMs)
    this.#prune()
  }

  has(token: string | undefined) {
    if (!token) return false
    this.#prune()
    return this.#until.has(this.#key(token))
  }

  entries() {
    return this.#until.entries()
  }
}
