export type Priority = 'critical' | 'high' | 'medium' | 'low'
/** Order of the operator queue: what needs a person first. */
export const priorities: readonly Priority[] = ['critical', 'high', 'medium', 'low']

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
