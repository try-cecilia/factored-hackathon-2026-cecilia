import type { Locale } from '../i18n/locales.ts'
import { htmlLang } from '../i18n/locales.ts'
import type { Translate } from '../i18n/translate.ts'
import type { TraceReceipt } from './types.ts'

export type ReceiptFact = { label: string; value: string }

/** One localized presentation shared by the chat card and copied conversation. */
export function traceReceiptFacts(receipt: TraceReceipt, locale: Locale, t: Translate) {
  const types: Record<string, string> = {
    Payment: t('chat.traceReceipt.types.payment'),
    Transfer: t('chat.traceReceipt.types.transfer'),
    Deposit: t('chat.traceReceipt.types.deposit'),
  }
  const movementStatuses: Record<string, string> = { Pending: t('chat.traceReceipt.status.pending') }
  const traceStatuses: Record<string, string> = { open: t('chat.traceReceipt.traceState.open') }
  const parsedDate = new Date(`${receipt.transaction_date}T00:00:00Z`)
  const date = Number.isNaN(parsedDate.getTime())
    ? receipt.transaction_date
    : new Intl.DateTimeFormat(htmlLang[locale], { dateStyle: 'medium', timeZone: 'UTC' }).format(parsedDate)
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
    ...(receipt.data_as_of ? [{
      label: t('chat.traceReceipt.dataAsOf'),
      value: new Intl.DateTimeFormat(htmlLang[locale], { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${receipt.data_as_of}T00:00:00Z`)),
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
