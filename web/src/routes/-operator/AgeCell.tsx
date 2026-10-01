import { useT } from '../../i18n/context'
import type { Locale } from '../../i18n/locales'
import type { QueueRow } from '../../server/queue-row'
import { AlertTriangleIcon } from '../../ui/messages/icons'
import { ageShort, when } from './format'
import { isOverdue, targetOf, targetShort } from './sla'

/**
 * How long a case has waited since it was handed to a person. An open case past its objective (sla.ts) is marked in amber, with
 * a glyph and words as well: the color alone would not reach everyone. The words are read once (the `title` sits on the hidden mark).
 */
export function AgeCell({ row, now, locale }: { row: QueueRow; now: number; locale: Locale }) {
  const t = useT()
  const created = t('operator.queue.ageTitle', { date: when(row.created_at, locale) })
  if (!isOverdue(row, now)) return <span title={created}>{ageShort(row.created_at, now)}</span>
  const late = t('operator.queue.overdue', { target: targetShort(targetOf(row)) })
  return (
    <span className="op-late" data-overdue="">
      <AlertTriangleIcon size={10} />
      <span aria-hidden="true" title={`${created}. ${late}`}>{ageShort(row.created_at, now)}</span>
      <span className="sr-only">{`${ageShort(row.created_at, now)}. ${late}`}</span>
    </span>
  )
}
