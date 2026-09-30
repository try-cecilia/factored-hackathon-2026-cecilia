import { useEffect, useState } from 'react'
import type { Session } from '../server/auth.functions'
import { sessionNotice } from './conversation'

// The instant a session ends is fixed the first time it is asked for, so the shell and the chat (each asks) count to the same one.
const deadlines = new WeakMap<Session, number>()

/**
 * What the session's countdown shows (`sessionNotice`): no notice, the minutes of the notice, or over. It ticks every five
 * seconds but holds that, not the seconds, so the page renders again only when what it shows changes.
 */
export function useSessionNotice(session: Session) {
  const [notice, setNotice] = useState(() => sessionNotice(session.expires_in))
  useEffect(() => {
    let deadline = deadlines.get(session)
    if (deadline === undefined) deadlines.set(session, (deadline = Date.now() + session.expires_in * 1000))
    const end = deadline
    const tick = () => setNotice(sessionNotice(Math.round((end - Date.now()) / 1000)))
    tick()
    const timer = setInterval(tick, 5_000)
    return () => clearInterval(timer)
  }, [session])
  return notice
}
