import { useEffect, useRef, useState } from 'react'
import type { Session } from '../server/auth.functions'
import { sessionNotice } from './conversation'

/**
 * What the session's countdown shows (`sessionNotice`): no notice, the minutes of the notice, or over. It ticks every five
 * seconds but holds that, not the seconds, so the page renders again only when what it shows changes. The end of a session is
 * counted from the first time it is seen and never moves later: another object of the same session (a loader that ran again)
 * cannot give it back the time it has already spent; one with less time to go does bring the end closer.
 */
export function useSessionNotice(session: Session) {
  const [notice, setNotice] = useState(() => sessionNotice(session.expires_in))
  const end = useRef<{ ref: string; at: number } | null>(null)
  useEffect(() => {
    const fresh = Date.now() + session.expires_in * 1000
    const known = end.current
    const at = known?.ref === session.session_ref ? Math.min(known.at, fresh) : fresh
    end.current = { ref: session.session_ref, at }
    const tick = () => setNotice(sessionNotice(Math.round((at - Date.now()) / 1000)))
    tick()
    const timer = setInterval(tick, 5_000)
    return () => clearInterval(timer)
  }, [session.session_ref, session.expires_in])
  return notice
}
