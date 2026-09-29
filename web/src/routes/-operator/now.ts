import { useEffect, useState } from 'react'

const MINUTE = 60_000

/**
 * The minute the queue's ages ("4m", "1h") are counted from. It moves on its own, so a table whose data did not change still
 * shows the right age; it reads nothing from the server (the queue's refresh is refresh.ts), and it changes once a minute, the
 * unit of an age, so the cells run again only when what they show can change.
 */
export function useMinute(): number {
  const [minute, setMinute] = useState(() => Math.floor(Date.now() / MINUTE) * MINUTE)
  useEffect(() => {
    const timer = setInterval(() => setMinute(Math.floor(Date.now() / MINUTE) * MINUTE), MINUTE / 4)
    return () => clearInterval(timer)
  }, [])
  return minute
}
