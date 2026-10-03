// The clock of the demo's session: it lasts a fixed time from the entry (SESSION_TTL_SECONDS, 15 minutes) and the bar warns in its
// last three. Pure, so the thresholds are tested without a DOM.

/** From this many seconds left the bar shows the countdown and the button to enter again. */
export const DEMO_WARN_SECONDS = 180

/** What the bar shows: nothing yet, the countdown, or that it is over. */
export type DemoClock = { state: 'running' } | { state: 'warning'; seconds: number } | { state: 'over' }

export function demoClock(secondsLeft: number): DemoClock {
  if (secondsLeft <= 0) return { state: 'over' }
  if (secondsLeft <= DEMO_WARN_SECONDS) return { state: 'warning', seconds: Math.ceil(secondsLeft) }
  return { state: 'running' }
}

/** 179 → "2:59". */
export const minutesSeconds = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
