// How often one address may enter the demo, free of framework code so a plain `node --test` can run it. Each entry is a real login
// (and the API limits those by address too, api/main.py): this one stops a loop before it reaches the API at all. In memory, per
// process, like the API's limiters: the web runs one instance.

const WINDOW_MS = 60_000
const DEFAULT_PER_MINUTE = 10
// Addresses are forgotten once their window is over; past this many at once, the oldest go first so the map cannot grow without end.
const MAX_KEYS = 10_000

export type Limiter = { take: (key: string, now?: number) => { ok: true } | { ok: false; retryAfter: number } }

export function perMinuteFromEnv(value: string | undefined): number {
  const n = Number(value)
  return Number.isInteger(n) && n > 0 ? n : DEFAULT_PER_MINUTE
}

/** A sliding window of `perMinute` entries per key. A refused call does not count: waiting is enough to get in again. */
export function createLimiter(perMinute: () => number): Limiter {
  const hits = new Map<string, number[]>()
  return {
    take(key, now = Date.now()) {
      const recent = (hits.get(key) ?? []).filter((at) => now - at < WINDOW_MS)
      if (recent.length >= perMinute()) {
        hits.set(key, recent)
        return { ok: false, retryAfter: Math.max(1, Math.ceil((recent[0] + WINDOW_MS - now) / 1000)) }
      }
      recent.push(now)
      hits.delete(key)
      hits.set(key, recent)
      if (hits.size > MAX_KEYS) hits.delete(hits.keys().next().value as string)
      return { ok: true }
    },
  }
}
