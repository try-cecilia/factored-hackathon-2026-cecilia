import type { QueueRow } from '../../server/queue-row.ts'

/**
 * Attention objective of a case: how long it may wait for a first person before the queue marks it. There is no case SLA
 * defined by the bank, so these numbers are a demo proposal, in one table, and docs/integracion.md says so. Fraud and
 * security are the shortest because the customer's money or access is at stake while they wait.
 */
export const TARGET_MINUTES = { security: 15, regulatory: 120, service: 240 } as const

export type Family = keyof typeof TARGET_MINUTES

const FAMILY_OF: Record<string, Family> = {
  fraud: 'security',
  theft: 'security',
  account_takeover: 'security',
  safety: 'security',
  security: 'security',
  classifier_escalation: 'security',
  legal_or_regulator: 'regulatory',
  compliance_hold: 'regulatory',
}

/** A category the table does not list (or none) gets the longest objective: it is not made more urgent than it is known to be. */
export const familyOf = (category: string | null | undefined): Family => (category && Object.hasOwn(FAMILY_OF, category) ? FAMILY_OF[category] : 'service')

/**
 * Whole minutes a case has waited past its objective, or null when it has not. Only an open case counts: once a person
 * takes it the objective (the wait for a first person) was met, and a decided one is history.
 */
export function overdueBy(row: QueueRow, now: number): number | null {
  if (row.desk.status !== 'open' || !row.created_at) return null
  const waited = (now - row.created_at * 1000) / 60_000
  const late = waited - TARGET_MINUTES[familyOf(row.category)]
  return late > 0 ? Math.floor(late) : null
}

export const isOverdue = (row: QueueRow, now: number) => overdueBy(row, now) !== null

/** The objective as a compact span, `15m` or `2h`; the units are the same in Spanish and Portuguese, as in the age column. */
export const targetShort = (minutes: number) => (minutes % 60 === 0 ? `${minutes / 60}h` : `${minutes}m`)

/** The objective that applies to a case. */
export const targetOf = (row: QueueRow) => TARGET_MINUTES[familyOf(row.category)]
