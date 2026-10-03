import { useI18n } from '../../i18n/context'
import { htmlLang } from '../../i18n/locales'
import type { MessageKey } from '../../i18n/translate'
import type { Json } from '../../server/operator.functions'

// The closed vocabularies of the rule catalog (agent/policy/payment_rules.py): a value outside them is shown as it came.
const OPERATIONS = ['Transfer', 'Payment', 'Deposit', 'Withdrawal', 'Purchase', 'Trace']
const KINDS = ['commission', 'deadline', 'threshold']

type Rule = Record<string, Json>
const text = (v: Json | undefined) => (typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '')
/** `2026-01-01` → `01/01/2026`; anything else as it came. */
const day = (v: Json | undefined) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(text(v))
  return m ? `${m[3]}/${m[2]}/${m[1]}` : text(v) || '—'
}

/** The result of `get_payment_conditions` on a ticket, in the operator's language: what the rule says, its scope, its validity and
 * its source, with the rule's id and URL kept as data. The customer was told none of it: the agent confirms it. */
export function PaymentRuleFact({ result }: { result: Record<string, Json> }) {
  const { t, locale } = useI18n()
  const key = (k: string) => `operator.ticket.paymentRule.${k}` as MessageKey
  const operation = text(result.operation)
  const rules = Array.isArray(result.rules) ? result.rules.filter((r): r is Rule => typeof r === 'object' && r !== null && !Array.isArray(r)) : []
  const value = (rule: Rule) => {
    const n = typeof rule.value === 'number' ? rule.value : Number.NaN
    const amount = Number.isFinite(n) ? new Intl.NumberFormat(htmlLang[locale], { maximumFractionDigits: 2 }).format(n) : text(rule.value)
    const unit = text(rule.unit)
    if (unit === 'business days' || unit === 'calendar days') {
      const base = unit === 'business days' ? 'businessDays' : 'calendarDays'
      return `${amount} ${t(key(`unit.${base}${n === 1 ? 'One' : 'Many'}`))}`
    }
    return unit === 'percent' ? `${amount} ${t(key('unit.percent'))}` : `${amount} ${unit}`
  }
  return (
    <div className="op-rule">
      <strong>{t(key('title'))}</strong>
      {rules.map((rule, i) => {
        const kind = text(rule.kind ?? result.kind)
        return (
          <dl key={i}>
            <dt>{t(key('rule'))}</dt>
            <dd>
              {[KINDS.includes(kind) ? t(key(`kind.${kind}`)) : kind, OPERATIONS.includes(operation) ? t(key(`operation.${operation}`)) : operation].join(' · ')}
              {' · '}<code>{text(rule.rule_id)} v{text(rule.version)}</code>
            </dd>
            <dt>{t(key('value'))}</dt><dd>{value(rule)}</dd>
            <dt>{t(key('scope'))}</dt><dd>{t(key('scopeText'), { country: text(result.country) || '—', currency: text(result.currency) || '—' })}</dd>
            <dt>{t(key('validity'))}</dt>
            <dd>{rule.valid_until ? t(key('fromUntil'), { from: day(rule.valid_from), until: day(rule.valid_until) }) : t(key('from'), { from: day(rule.valid_from) })}</dd>
            <dt>{t(key('source'))}</dt>
            <dd>
              {text(rule.source_issuer)} · {/^https:\/\//.test(text(rule.source_url))
                ? <a href={text(rule.source_url)} target="_blank" rel="noreferrer noopener">{text(rule.source_url)}</a>
                : text(rule.source_url)}
              {' · '}{t(key('checked'), { date: day(rule.source_checked_at) })}
            </dd>
          </dl>
        )
      })}
    </div>
  )
}
