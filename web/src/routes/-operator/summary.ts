import type { Translate } from '../../i18n/translate.ts'
import type { Ticket } from '../../server/operator.functions.ts'
import { categoryName, statusKey } from './format.ts'
import { nextStepText, reasonText } from './notes.ts'

/** Score at which the desk marks a transaction (agent/policy/escalation.py: FRAUD_SCORE_FLAG). */
export const FRAUD_SCORE_FLAG = 70

type Evidence = Ticket['evidence'][number]

const scoreOf = (e: Evidence) => {
  const score = e.detail.fraud_score
  return typeof score === 'number' ? score : typeof score === 'string' && score.trim() !== '' ? Number(score) : null
}

/** A transaction is marked when the API flagged it or its fraud score reaches 70. */
export const isFlagged = (e: Evidence) => e.type === 'transaction' && (e.flagged === true || (scoreOf(e) ?? -1) >= FRAUD_SCORE_FLAG)

export const scoreLabel = (e: Evidence) => {
  const score = scoreOf(e)
  return score === null || Number.isNaN(score) ? '—' : String(score)
}

/** Plain text the operator pastes into another system: what the case is, where it stands and what was flagged. Nothing the customer typed beyond the request. */
export function ticketSummary(ticket: Ticket, t: Translate): string {
  const flagged = ticket.evidence.filter(isFlagged).map((e) => e.id).filter(Boolean)
  return [
    t('operator.ticket.summary.title', { id: ticket.ticket_id.slice(0, 8), queue: ticket.queue }),
    t('operator.ticket.summary.priority', { priority: ticket.priority || t('table.priority.unknown') }),
    t('operator.ticket.summary.status', { status: `${t(statusKey[ticket.desk.status])}${ticket.desk.operator ? ` (${ticket.desk.operator})` : ''}` }),
    `${categoryName(t, ticket.category)} · v${ticket.desk.version}`,
    t('operator.ticket.summary.request', { request: ticket.request }),
    t('operator.ticket.summary.reason', { reason: reasonText(t, ticket) }),
    t('operator.ticket.summary.nextStep', { step: nextStepText(t, ticket) }),
    ...(flagged.length ? [t('operator.ticket.summary.flagged', { list: flagged.join(', ') })] : []),
    ...(ticket.desk.trace_id ? [t('operator.ticket.summary.trace', { id: ticket.desk.trace_id })] : []),
  ].join('\n')
}
