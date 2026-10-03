import { useEffect, useRef, useState } from 'react'
import { demoClock, type DemoClock } from './expiry'

/**
 * The demo's countdown for one session, from the seconds the API says it has left. As the chat's own notice (useSessionNotice), the
 * end is fixed the first time a session is seen and never moves later; a reading with less time left brings it closer.
 */
export function useDemoClock(sessionRef: string | null, expiresIn: number | null): DemoClock {
  const [clock, setClock] = useState<DemoClock>(() => (expiresIn === null ? { state: 'running' } : demoClock(expiresIn)))
  const end = useRef<{ ref: string; at: number } | null>(null)
  useEffect(() => {
    if (sessionRef === null || expiresIn === null) return
    const fresh = Date.now() + expiresIn * 1000
    const known = end.current
    const at = known?.ref === sessionRef ? Math.min(known.at, fresh) : fresh
    end.current = { ref: sessionRef, at }
    // Only what the bar shows: a second that changes nothing on screen renders nothing.
    const tick = () => {
      const next = demoClock((at - Date.now()) / 1000)
      setClock((prev) => (prev.state === next.state && (prev.state !== 'warning' || prev.seconds === (next as { seconds: number }).seconds) ? prev : next))
    }
    tick()
    const timer = setInterval(tick, 1_000)
    return () => clearInterval(timer)
  }, [sessionRef, expiresIn])
  return clock
}
