import type { MessageKey, Params, Translate } from '../../i18n/translate.ts'
import type { Messages } from '../../i18n/types.ts'
import type { Ticket } from '../../server/operator.functions.ts'
import { categoryName } from './format.ts'

/**
 * The texts the operator reads on a case come from the API as a code with its parameters (agent/policy/notes.py) next to the
 * English text they always had. The code is written in the operator's language; a case filed before the codes has none, and a
 * code this console does not know is not an error: both show the English text as it came, never nothing.
 */
export type Coded = { code: string; params?: Params }

// A code is a plain identifier: it becomes part of a dictionary path, so nothing with a dot or a slash in it gets in.
const IDENT = /^\w+$/

/** The text of a dictionary key, or `undefined` when it has none: `t` answers a missing key with the key itself. */
function translated(t: Translate, key: string, params?: Params): string | undefined {
  const text = t(key as MessageKey, params)
  return text === key || /\{\w+\}/.test(text) ? undefined : text // a placeholder left unfilled is a text without its data
}

const named = (t: Translate, group: string, id: string | null | undefined) =>
  id && IDENT.test(id) ? translated(t, `operator.terms.${group}.${id}`) ?? id : id ?? '—'

/** Why a review was needed, in words; a reason it does not know stays as the code. */
export const reviewReasonName = (t: Translate, code: string | null | undefined) => named(t, 'reviewReason', code)
/** "transaction" → "Movimiento". */
export const evidenceTypeName = (t: Translate, type: string) => named(t, 'evidenceType', type)
/** A key of a fact or of an evidence detail: `tool` → "Herramienta". */
export const keyName = (t: Translate, key: string) => named(t, 'key', key)
export const attemptOutcomeName = (t: Translate, outcome: string | null | undefined) => named(t, 'attempt.outcome', outcome)
export const errorTypeName = (t: Translate, type: string | null | undefined) => named(t, 'errorType', type)

/** Some parameters name something that has its own translation: a list of categories, a review reason. */
function paramsOf(t: Translate, params: Params | undefined): Params | undefined {
  if (!params) return params
  const out: Params = { ...params }
  if (typeof out.categories === 'string') out.categories = out.categories.split(', ').map((c) => categoryName(t, c)).join(', ')
  if (typeof out.review_reason === 'string') out.review_reason = reviewReasonName(t, out.review_reason)
  return out
}

/** A parameter with a value: a text that says something, or a number (zero is one). Anything else would print as "null" or "()". */
const hasValue = (value: unknown) => (typeof value === 'string' ? value.trim() !== '' : typeof value === 'number' && Number.isFinite(value))

function coded(t: Translate, kind: 'reason' | 'question' | 'step', item: Coded | null | undefined, english: string): string {
  if (!item || typeof item.code !== 'string' || !IDENT.test(item.code)) return english
  if (item.params && !Object.values(item.params).every(hasValue)) return english
  return translated(t, `operator.codes.${kind}.${item.code}`, paramsOf(t, item.params)) ?? english
}

export type Texts = Pick<Ticket, 'reason' | 'reason_code' | 'open_questions' | 'open_question_codes' | 'suggested_next_step' | 'next_step_code'>

export const reasonText = (t: Translate, ticket: Texts) => coded(t, 'reason', ticket.reason_code, ticket.reason)

/** One per open question: the code at the same position when the case has codes, and the English text where it has none. */
export const questionTexts = (t: Translate, ticket: Texts) =>
  ticket.open_questions.map((question, i) => coded(t, 'question', ticket.open_question_codes?.[i], question))

export const nextStepText = (t: Translate, ticket: Texts) =>
  coded(t, 'step', ticket.next_step_code ? { code: ticket.next_step_code } : null, ticket.suggested_next_step)

type RuleName = keyof Messages['operator']['terms']['rule']

// The policy rules the API and the traces carry (agent/policy/router.py, agent/core/orchestrator.py): the whole rule, or its family
// before the colon with what follows as the detail.
const wholeRules: Record<string, RuleName> = {
  'customer_status == Suspended': 'suspended',
  'intent_classifier:requires_escalation': 'classifierEscalation',
  'intent_classifier:out_of_scope': 'classifierOutOfScope',
  'fallback:punctuation': 'punctuation',
  reference_to_foreign_product: 'foreignProduct',
  llm_unavailable: 'llmUnavailable',
  turn_timeout: 'turnTimeout',
  unexpected_failure: 'unexpectedFailure',
  verified_tool_results: 'verifiedResults',
  'degraded:classifier_out_of_scope': 'degradedOutOfScope',
  'degraded:deterministic_balance': 'degradedBalance',
  'action:trace_unmatched': 'traceUnmatched',
  'action:trace_choose': 'traceChoose',
  'action:trace_already_open': 'traceAlreadyOpen',
  'action:trace_proposed': 'traceProposed',
  'action:trace_opened': 'traceOpened',
  'action:trace_unverified': 'traceUnverified',
  'action:trace_review': 'traceReview',
  'action:trace_cancelled': 'traceCancelled',
}
const ruleFamilies: Record<string, RuleName> = { lexicon: 'lexicon', intent_classifier: 'classifier', tool_error: 'toolError', session: 'session' }

/** A policy rule in words; one it does not know is shown as it came. */
export function ruleName(t: Translate, rule: string | null | undefined): string {
  if (!rule) return '—'
  const [base, ...marks] = rule.split('|')
  const key = (name: RuleName) => `operator.terms.rule.${name}`
  const family = base.split(':')[0]
  let text: string | undefined
  if (Object.hasOwn(wholeRules, base)) text = translated(t, key(wholeRules[base]))
  else if (Object.hasOwn(ruleFamilies, family) && base.includes(':')) {
    const detail = base.slice(family.length + 1)
    text = translated(t, key(ruleFamilies[family]), { detail: family === 'lexicon' ? categoryName(t, detail) : detail })
  }
  if (text === undefined) return rule
  const marked = marks.map((mark) => (mark === 'handoff_unverified' ? translated(t, key('handoffUnverified')) : undefined) ?? mark)
  return [text, ...marked].join(' · ')
}

/** Why a model attempt was skipped: a code (`circuit_open`) or "<KEY> not set"; anything else stays as it came. */
export function attemptReasonName(t: Translate, reason: string | null | undefined): string {
  if (!reason) return '—'
  const missing = /^(\w+) not set$/.exec(reason)
  if (missing) return translated(t, 'operator.terms.attempt.reason.keyNotSet', { name: missing[1] }) ?? reason
  return named(t, 'attempt.reason', reason)
}
