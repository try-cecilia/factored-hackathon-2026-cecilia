/**
 * The 409 locks that are in force, by case. They live outside the panel because an error higher up the route tree (the
 * console's own layout failing to reach the BFF) unmounts the panel, and a lock that disappears with it would let the operator
 * decide on a screen they were told is out of date. A lock goes away only when a complete reload of that case ends well; a
 * full page load starts clean, which is also a complete read.
 */
export type Conflict = { seen: number; detail?: string }

const held = new Map<string, Conflict>()

export const conflictOf = (ticketId: string): Conflict | null => held.get(ticketId) ?? null

export function holdConflict(ticketId: string, conflict: Conflict | null) {
  if (conflict) held.set(ticketId, conflict)
  else held.delete(ticketId)
}

/** For tests. */
export const dropConflicts = () => held.clear()
