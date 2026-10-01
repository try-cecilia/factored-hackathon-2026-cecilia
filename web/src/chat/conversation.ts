// What the chat screen keeps and decides, without React: the entries of the conversation, how a failed send is worded, which
// message component a reply gets, and which cases the conversation has opened. Pure so it is tested without a DOM.
import { resolveMessage } from '../ui/messages/disposition.ts'
import type { DeliveryState } from '../ui/loaders/delivery.ts'
import { parseOptions, type Options } from './format.ts'
import type { HistoryCase, HistoryEntry, Reply, SendFailure } from './types.ts'

export type UserEntry = {
  id: number
  role: 'user'
  text: string
  at: number
  /** The Idempotency-Key of the message. A message read back from the history has none: it is not sent again. */
  key: string | null
  delivery: DeliveryState
  failure?: FailureKind
}
/** Why a message did not go through. `ended`: the session was over, so nothing was sent. `answer_gone`: the API has the message
 * but no longer has its reply (the idempotency table dropped it and the reload does not bring it back). */
export type FailureKind = Exclude<SendFailure, 'session_expired'> | 'ended' | 'answer_gone'
/** `to` is the id of the user entry the reply answers: a reply that arrives late (a retry) is not by its side in the conversation.
 * A reply read back from the history has none: it answers the message before it. */
export type AssistantEntry = { id: number; role: 'assistant'; reply: Reply; at: number; to?: number }
/** An event of the conversation, not a message. */
export type NoteEntry = { id: number; role: 'note'; note: 'restored'; at: number }
export type Entry = UserEntry | AssistantEntry | NoteEntry

/** Numbers the entries read back from the history from `firstId`, and closes them with the "conversation resumed" note. */
export function fromHistory(turns: HistoryEntry[], firstId: number, now: number): Entry[] {
  if (turns.length === 0) return []
  const entries: Entry[] = turns.map((turn, i) =>
    turn.role === 'user'
      ? { id: firstId + i, role: 'user', text: turn.text, at: turn.at, key: null, delivery: 'sent' }
      : { id: firstId + i, role: 'assistant', reply: turn.reply, at: turn.at },
  )
  entries.push({ id: firstId + turns.length, role: 'note', note: 'restored', at: now })
  return entries
}

/** After a lost answer nobody knows whether the message arrived (uncertain, safe to retry with the same key); a refused
 * one never ran (failed); a 409 means the API has it and only the conversation can show the reply (processed). */
export function deliveryOf(failure: FailureKind): DeliveryState {
  switch (failure) {
    case 'already_processed':
    case 'answer_gone':
      return 'processed'
    case 'rate_limited':
    case 'busy':
    case 'ended':
      return 'failed'
    default:
      return 'uncertain'
  }
}

export type DeliveryDetailKey = 'uncertain' | 'timeout' | 'rateLimited' | 'busy' | 'unexpected' | 'processed' | 'processedGone' | 'ended'

export function deliveryDetailKey(failure: FailureKind): DeliveryDetailKey {
  switch (failure) {
    case 'unavailable':
      return 'uncertain'
    case 'rate_limited':
      return 'rateLimited'
    case 'already_processed':
      return 'processed'
    case 'answer_gone':
      return 'processedGone'
    default:
      return failure
  }
}

// What the customer's plain yes and no look like in each language. The API judges them in code; these only tell the screen
// how a proposal ended.
const YES = new Set(['si', 'sim', 'sí'])
const NO = new Set(['no', 'não', 'nao'])
const plain = (text: string) => text.trim().toLowerCase().replace(/[.!¡]+$/g, '')
export const isYes = (text: string) => YES.has(plain(text))
export const isNo = (text: string) => NO.has(plain(text))

export type ReplyKind =
  | { kind: 'answer' }
  | { kind: 'clarify'; options: Options | null }
  | { kind: 'confirmTrace' }
  | { kind: 'actionResult' }
  | { kind: 'decline' }
  | { kind: 'handoff'; ticketId: string; category: string }
  | { kind: 'couldNotVerify' }
  | { kind: 'signInAgain' }

const isProposal = (reply: Reply) => reply.disposition === 'CLARIFY' && reply.category === 'confirm_action'

/**
 * Which component draws a reply. The disposition decides (the kit's `resolveMessage`); the API's category and the turn before
 * refine it: a proposal to trace is CLARIFY + confirm_action; the answer to the customer's yes to a proposal is the action
 * result; a handoff with no case number means the case could not be filed, so it is "could not verify"; the customer's no
 * ("nothing opened") is an answer, not a refusal.
 */
export function classifyReply(reply: Reply, before: readonly Entry[] = []): ReplyKind {
  const { variant } = resolveMessage({ disposition: reply.disposition })
  if (variant === 'clarify') return isProposal(reply) ? { kind: 'confirmTrace' } : { kind: 'clarify', options: parseOptions(reply.response_text, reply.choice) }
  if (variant === 'decline') return reply.category === 'action_cancelled' ? { kind: 'answer' } : { kind: 'decline' }
  if (variant === 'handoff') return reply.ticket_id ? { kind: 'handoff', ticketId: reply.ticket_id, category: reply.category } : { kind: 'couldNotVerify' }
  if (variant === 'answer' && answersAYes(before)) return { kind: 'actionResult' }
  if (variant === 'answer') return { kind: 'answer' }
  return { kind: variant }
}

/** The reply follows the customer's yes to a proposal to trace: what it says was opened by that yes. */
function answersAYes(before: readonly Entry[]): boolean {
  const messages = before.filter((e) => e.role !== 'note')
  const yes = messages.at(-1)
  const proposal = messages.at(-2)
  return yes?.role === 'user' && isYes(yes.text) && proposal?.role === 'assistant' && isProposal(proposal.reply)
}

export type ProposalState = 'idle' | 'loading' | 'sent' | 'declined'

/** Where a proposal to trace stands, from what came after it: waiting, the yes in flight, yes, or no (or anything else, which lets it lapse). */
export function proposalState(entries: readonly Entry[], index: number, sending: boolean): ProposalState {
  const answer = entries.slice(index + 1).find((e) => e.role === 'user')
  if (!answer || answer.role !== 'user') return 'idle'
  if (isYes(answer.text)) return sending && answer.delivery === 'sending' ? 'loading' : answer.delivery === 'sent' ? 'sent' : 'idle'
  return 'declined'
}

/** The option the customer chose from a clarification, if the next message is one of them. */
export function chosenOption(options: Options, answer: (i: number) => string, next: Entry | undefined): number | undefined {
  if (next?.role !== 'user') return undefined
  const index = options.options.findIndex((_, i) => answer(i) === next.text)
  return index < 0 ? undefined : index
}

const NEWS = /^(Novedad de tu caso|Novidade do seu caso):/

/** What a person did with the customer's cases arrives in the reply's first lines ("Novedad de tu caso: ..."); the screen shows them as notes. */
export function splitCaseNews(text: string): { news: string[]; body: string } {
  const lines = text.split('\n')
  const news: string[] = []
  while (lines.length && (NEWS.test(lines[0].trim()) || (!lines[0].trim() && news.length && lines.slice(1).some((l) => NEWS.test(l.trim()))))) {
    const line = lines.shift() as string
    if (line.trim()) news.push(line.trim())
  }
  return { news, body: lines.join('\n').trim() }
}

const UUID = /^([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** A case number short enough for a list ("55d09c14"); the full one is what the handoff message shows. */
export function shortCaseId(ticketId: string): string {
  return UUID.exec(ticketId)?.[1] ?? ticketId
}

export type CaseRef = HistoryCase

/** The cases the conversation has opened, newest first. A case is a handoff that came with a number. */
export function casesOf(entries: readonly Entry[]): CaseRef[] {
  const seen = new Set<string>()
  const found: CaseRef[] = []
  for (const entry of [...entries].reverse()) {
    if (entry.role !== 'assistant' || entry.reply.disposition !== 'ESCALATE' || !entry.reply.ticket_id) continue
    if (seen.has(entry.reply.ticket_id)) continue
    seen.add(entry.reply.ticket_id)
    found.push({ ticketId: entry.reply.ticket_id, category: entry.reply.category, at: entry.at })
  }
  return found
}

/** The cases the API kept for the session (they outlive the bounded turns) and the ones this page saw open, newest first, once each. */
export function mergeCases(kept: readonly CaseRef[], seen: readonly CaseRef[]): CaseRef[] {
  const byId = new Map<string, CaseRef>()
  for (const c of [...kept, ...seen]) if (!byId.has(c.ticketId)) byId.set(c.ticketId, c)
  return [...byId.values()].sort((a, b) => b.at - a.at)
}

/** A case a person has not decided yet can still change; the rest is final. */
export const isOpenCase = (status: string) => status === 'open' || status === 'claimed'

export type CaseTone = 'accent' | 'success' | 'caution' | 'danger'

export function caseTone(status: string): CaseTone {
  switch (status) {
    case 'open':
    case 'claimed':
      return 'accent'
    case 'approved':
    case 'resolved':
      return 'success'
    case 'rejected':
      return 'danger'
    case 'stale':
      return 'caution'
    default:
      return 'accent' // in hand, or not known yet: the blue of the agent's state
  }
}

const KNOWN_CATEGORIES = new Set([
  'fraud', 'theft', 'account_takeover', 'safety', 'legal_or_regulator', 'classifier_escalation', 'compliance_hold', 'security',
  'trace_unmatched', 'trace_unverified', 'trace_review',
])
// The turn failed or ran out of time before it could answer: the customer only needs to know it is with a person.
const PENDING = new Set(['data_unavailable', 'tool_failure', 'llm_unavailable', 'turn_timeout'])

/** The dictionary key (under `cases.category`) that names a case for the customer. */
export function caseCategoryKey(category: string): string {
  if (KNOWN_CATEGORIES.has(category)) return category
  return PENDING.has(category) ? 'pending' : 'other'
}

const WARN_SECONDS = 120

/**
 * What the session's countdown shows with `seconds` left: `null` while there is time (no notice), the minutes of the notice once
 * two are left (2, then 1), and 0 when it is over.
 */
export function sessionNotice(seconds: number): number | null {
  if (seconds <= 0) return 0
  if (seconds > WARN_SECONDS) return null
  return Math.max(1, Math.ceil(seconds / 60))
}
