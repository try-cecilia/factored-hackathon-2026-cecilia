import type { MessageKey, Translate } from '../../i18n/translate.ts'

// The warehouse names things in its own words (product types in Spanish, statuses in English). The console says them in the operator's
// language, and a value it does not know is shown as it came, never hidden.
const PRODUCT_TYPES: Record<string, MessageKey> = {
  'Cuenta Ahorro': 'operator.context.productType.savings',
  'Cuenta Corriente': 'operator.context.productType.checking',
  'Tarjeta Débito': 'operator.context.productType.debit',
  'Tarjeta Crédito': 'operator.context.productType.credit',
  'Préstamo Hipotecario': 'operator.context.productType.mortgage',
  'Préstamo Personal': 'operator.context.productType.loan',
  Inversión: 'operator.context.productType.investment',
  Seguro: 'operator.context.productType.insurance',
}
const PRODUCT_STATUSES: Record<string, MessageKey> = {
  Active: 'operator.context.productStatus.Active',
  Blocked: 'operator.context.productStatus.Blocked',
  Suspended: 'operator.context.productStatus.Suspended',
  Closed: 'operator.context.productStatus.Closed',
}
const MOVEMENT_TYPES: Record<string, MessageKey> = {
  Payment: 'operator.context.movementType.Payment',
  Purchase: 'operator.context.movementType.Purchase',
  Transfer: 'operator.context.movementType.Transfer',
  Withdrawal: 'operator.context.movementType.Withdrawal',
  Deposit: 'operator.context.movementType.Deposit',
  Adjustment: 'operator.context.movementType.Adjustment',
}
const MOVEMENT_STATUSES: Record<string, MessageKey> = {
  Approved: 'operator.context.movementStatus.Approved',
  Reversed: 'operator.context.movementStatus.Reversed',
  Pending: 'operator.context.movementStatus.Pending',
  Declined: 'operator.context.movementStatus.Declined',
}
const TRACE_STATUSES: Record<string, MessageKey> = { open: 'operator.context.traceStatus.open' }

const named = (keys: Record<string, MessageKey>, t: Translate, value: string | null | undefined) =>
  value ? (Object.hasOwn(keys, value) ? t(keys[value]) : value) : '—'

export const productTypeName = (t: Translate, value: string | null | undefined) => named(PRODUCT_TYPES, t, value)
export const productStatusName = (t: Translate, value: string | null | undefined) => named(PRODUCT_STATUSES, t, value)
export const movementTypeName = (t: Translate, value: string | null | undefined) => named(MOVEMENT_TYPES, t, value)
export const movementStatusName = (t: Translate, value: string | null | undefined) => named(MOVEMENT_STATUSES, t, value)
export const traceStatusName = (t: Translate, value: string | null | undefined) => named(TRACE_STATUSES, t, value)

/** A product's mark as the operator reads it: the last four digits behind dots, never more. */
export const maskOf = (last4: string | null) => (last4 ? `•••• ${last4}` : '••••')
