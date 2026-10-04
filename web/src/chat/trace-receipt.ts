import type { Locale } from '../i18n/locales.ts'
import { htmlLang } from '../i18n/locales.ts'
import type { Translate } from '../i18n/translate.ts'
import type { TraceReceipt } from './types.ts'

export type ReceiptFact = { label: string; value: string }

function formatDate(value: string, locale: Locale): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) return null
  return new Intl.DateTimeFormat(htmlLang[locale], { dateStyle: 'medium', timeZone: 'UTC' }).format(parsed)
}

/** One localized presentation shared by the chat card and copied conversation. */
export function traceReceiptFacts(receipt: TraceReceipt, locale: Locale, t: Translate) {
  const types: Record<string, string> = {
    Payment: t('chat.traceReceipt.types.payment'),
    Transfer: t('chat.traceReceipt.types.transfer'),
    Deposit: t('chat.traceReceipt.types.deposit'),
  }
  const movementStatuses: Record<string, string> = { Pending: t('chat.traceReceipt.status.pending') }
  const traceStatuses: Record<string, string> = { open: t('chat.traceReceipt.traceState.open') }
  const date = formatDate(receipt.transaction_date, locale) ?? receipt.transaction_date
  const dataAsOf = receipt.data_as_of ? formatDate(receipt.data_as_of, locale) : null
  let amount: string
  try {
    amount = new Intl.NumberFormat(htmlLang[locale], {
      style: 'currency', currency: receipt.currency, currencyDisplay: 'code',
    }).format(receipt.amount)
  } catch {
    amount = `${receipt.amount.toLocaleString(htmlLang[locale])} ${receipt.currency}`
  }
  const facts: ReceiptFact[] = [
    { label: t('chat.traceReceipt.movement'), value: `${types[receipt.transaction_type] ?? receipt.transaction_type} · ${receipt.transaction_id}` },
    { label: t('chat.traceReceipt.date'), value: date },
    ...(receipt.source === 'account_records' ? [{ label: t('chat.traceReceipt.source'), value: t('chat.traceReceipt.accountRecords') }] : []),
    ...(dataAsOf ? [{
      label: t('chat.traceReceipt.dataAsOf'),
      value: dataAsOf,
    }] : []),
    { label: t('chat.traceReceipt.amount'), value: amount },
    { label: t('chat.traceReceipt.movementStatus'), value: movementStatuses[receipt.movement_status] ?? receipt.movement_status },
    { label: t('chat.traceReceipt.traceStatus'), value: traceStatuses[receipt.trace_status] ?? receipt.trace_status },
    { label: t('chat.traceReceipt.readBack'), value: t('chat.traceReceipt.readBackConfirmed') },
  ]
  // No source-backed rule, no deadline: the receipt says so instead of promising one.
  const nextStep = receipt.sla_business_days === null
    ? t('chat.traceReceipt.nextStepNoDeadline')
    : t(receipt.sla_business_days === 1 ? 'chat.traceReceipt.nextStepOne' : 'chat.traceReceipt.nextStepMany',
      { n: receipt.sla_business_days })
  return { facts, nextStep }
}
