import './DataInAnswer.css'

/** One line of data: a movement or a balance. Everything arrives formatted in the customer's language. */
export type DataInAnswerRow = {
  /** Optional lead column, usually the date ("Aug 29"). */
  leading?: string
  label: string
  /** Amount or balance, right aligned with tabular numerals. */
  value: string
}

export type DataInAnswerProps = {
  rows: DataInAnswerRow[]
  /** Names the list for assistive tech ("Your three biggest dining charges"). Already in the customer's language. */
  label: string
  className?: string
}

/** Data inside a reply: comfortable 40px rows on a tonal panel, every other row lifted on paper. */
export function DataInAnswer({ rows, label, className }: DataInAnswerProps) {
  const hasLeading = rows.some((row) => row.leading)
  const classes = ['ui-data', hasLeading && 'ui-data--leading', className].filter(Boolean).join(' ')
  return (
    <ul className={classes} role="list" aria-label={label}>
      {rows.map((row, i) => (
        <li key={`${row.leading ?? ''}|${row.label}|${i}`} className="ui-data__row">
          {hasLeading && <span className="ui-data__leading">{row.leading}</span>}
          <span className="ui-data__label">{row.label}</span>
          <span className="ui-data__value">{row.value}</span>
        </li>
      ))}
    </ul>
  )
}
