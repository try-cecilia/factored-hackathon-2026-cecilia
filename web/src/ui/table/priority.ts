export type Priority = 'critical' | 'high' | 'medium' | 'low'
/** Order of the operator queue: what needs a person first. */
export const priorities: readonly Priority[] = ['critical', 'high', 'medium', 'low']

/** The chip of a case whose priority is missing or not one of the four: it says so instead of taking one of them. */
export type KnownPriority = Priority | 'unknown'

/** A priority as the API sends it ("High") in the kit's terms; a missing one, or one it does not know, is `unknown`. */
export function priorityOf(value: string | null | undefined): KnownPriority {
  const key = typeof value === 'string' ? value.toLowerCase() : ''
  return (priorities as readonly string[]).includes(key) ? (key as Priority) : 'unknown'
}

/** 0 is the most urgent. Unknown values sort after every known one. */
export function priorityRank(priority: string): number {
  const index = priorities.indexOf(priority as Priority)
  return index === -1 ? priorities.length : index
}

export function comparePriority(a: string, b: string): number {
  return priorityRank(a) - priorityRank(b)
}

/** Dot in front of a status label. Amber (`caution`) is only for "wait, look at this": pending, stale. `danger` is a refusal. */
export type StatusTone = 'neutral' | 'info' | 'success' | 'caution' | 'open' | 'danger'
