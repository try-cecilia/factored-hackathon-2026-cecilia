import { htmlLang, type Locale } from '../../i18n/locales.ts'
import type { MessageKey, Translate } from '../../i18n/translate.ts'
import type { DeskStatus } from '../../server/operator.functions.ts'

export const CLOSED: readonly DeskStatus[] = ['approved', 'rejected', 'handed_back', 'stale']

export const statusKey: Record<DeskStatus, MessageKey> = {
  open: 'operator.status.open',
  claimed: 'operator.status.claimed',
  approved: 'operator.status.approved',
  rejected: 'operator.status.rejected',
  handed_back: 'operator.status.handed_back',
  stale: 'operator.status.stale',
}

const categoryKeys = {
  fraud: 'operator.category.fraud',
  theft: 'operator.category.theft',
  account_takeover: 'operator.category.account_takeover',
  safety: 'operator.category.safety',
  legal_or_regulator: 'operator.category.legal_or_regulator',
  classifier_escalation: 'operator.category.classifier_escalation',
  compliance_hold: 'operator.category.compliance_hold',
  security: 'operator.category.security',
  data_unavailable: 'operator.category.data_unavailable',
  tool_failure: 'operator.category.tool_failure',
  llm_unavailable: 'operator.category.llm_unavailable',
  trace_unmatched: 'operator.category.trace_unmatched',
  trace_unverified: 'operator.category.trace_unverified',
  trace_review: 'operator.category.trace_review',
} as const satisfies Record<string, MessageKey>

const dispositionKeys = {
  AUTO_RESOLVE: 'operator.disposition.AUTO_RESOLVE',
  CLARIFY: 'operator.disposition.CLARIFY',
  ABSTAIN: 'operator.disposition.ABSTAIN',
  ESCALATE: 'operator.disposition.ESCALATE',
  REAUTH_REQUIRED: 'operator.disposition.REAUTH_REQUIRED',
} as const satisfies Record<string, MessageKey>

const named = (keys: Record<string, MessageKey>, t: Translate, key: string | null | undefined) =>
  key ? (Object.hasOwn(keys, key) ? t(keys[key]) : key) : '—'

/** A category the console does not know yet is shown as the API sent it, never hidden. */
export const categoryName = (t: Translate, key: string | null | undefined) => named(categoryKeys, t, key)
export const dispositionName = (t: Translate, key: string | null | undefined) => named(dispositionKeys, t, key)

/** Queue-table age: `4m`, `1h`, `2d`. Units are the same in Spanish and Portuguese, so it needs no dictionary. */
export function ageShort(ts: number | null | undefined, now = Date.now()) {
  if (!ts) return '—'
  const seconds = Math.max(0, Math.round((now - ts * 1000) / 1000))
  if (seconds < 60) return '<1m'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

/** "hace 4 min" / "há 4 min", for sentences. */
// One formatter per language and kind, made once: building an Intl formatter costs far more than using it, and a table asks per cell.
const formatters = new Map<string, Intl.DateTimeFormat | Intl.RelativeTimeFormat>()
function cached<F extends Intl.DateTimeFormat | Intl.RelativeTimeFormat>(key: string, make: () => F): F {
  let formatter = formatters.get(key) as F | undefined
  if (!formatter) formatters.set(key, (formatter = make()))
  return formatter
}
const relative = (locale: Locale) => cached(`relative:${locale}`, () => new Intl.RelativeTimeFormat(htmlLang[locale], { numeric: 'auto' }))
const dateTime = (locale: Locale) => cached(`dateTime:${locale}`, () => new Intl.DateTimeFormat(htmlLang[locale], { dateStyle: 'medium', timeStyle: 'short' }))
const hourMinute = (locale: Locale) => cached(`hourMinute:${locale}`, () => new Intl.DateTimeFormat(htmlLang[locale], { hour: '2-digit', minute: '2-digit' }))

export function ago(ts: number | null | undefined, locale: Locale, now = Date.now()) {
  if (!ts) return '—'
  const rtf = relative(locale)
  const seconds = Math.round((ts * 1000 - now) / 1000)
  const abs = Math.abs(seconds)
  if (abs < 60) return rtf.format(0, 'second')
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), 'hour')
  return rtf.format(Math.round(seconds / 86400), 'day')
}

export const when = (ts: number | null | undefined, locale: Locale) => (ts ? dateTime(locale).format(ts * 1000) : '—')

/** `MM-DD HH:mm`, the compact stamp of the evidence rows. */
export function shortStamp(value: unknown) {
  const match = typeof value === 'string' ? /(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(value) : null
  return match ? `${match[2]}-${match[3]}${match[4] ? ` ${match[4]}` : ''}` : '—'
}

export const clock = (ts: number, locale: Locale) => hourMinute(locale).format(ts * 1000)

export const usd = (n: number | null | undefined, digits = 4) => (n == null ? '—' : `USD ${n.toFixed(digits)}`)
export const ms = (n: number | null | undefined) => (n == null ? '—' : n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${Math.round(n)} ms`)
export const short = (id: string | null | undefined) => (id ? id.slice(0, 8) : '—')

/** `8450 MXN` → `8,450.00 MXN`; leaves what is not a number alone. */
export function money(amount: unknown, currency: unknown) {
  const n = typeof amount === 'number' ? amount : typeof amount === 'string' && amount.trim() !== '' ? Number(amount) : NaN
  const value = Number.isFinite(n) ? n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'
  return currency ? `${value} ${String(currency)}` : value
}

/** What the operator reads when the BFF or API said no. `acting` = the failed call was an action, not a read. */
export function explainKey(status: number, acting = false): MessageKey {
  switch (status) {
    case 0:
    case 401:
      return acting ? 'operator.errors.expiredActing' : 'operator.errors.expired'
    case 403:
      return 'operator.errors.readOnly'
    case 404:
      return acting ? 'operator.errors.notFoundActing' : 'operator.errors.notFound'
    case 409:
      return 'operator.errors.conflict'
    case 429:
      return 'operator.errors.tooMany'
    case 503:
      return 'operator.errors.unavailable'
    default:
      return 'operator.errors.generic'
  }
}
