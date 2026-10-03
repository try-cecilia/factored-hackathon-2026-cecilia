import type { ReactNode } from 'react'

/** The small uppercase line above a section title: cecil blue, or gray when `muted`. The black section paints it sky. */
export function Eyebrow({ children, muted }: { children: ReactNode; muted?: boolean }) {
  return <p className={muted ? 'land-eyebrow land-eyebrow--muted' : 'land-eyebrow'}>{children}</p>
}

export type TableRow = {
  label: ReactNode
  cells: ReactNode[]
  /** The row that carries the claim: bold label. */
  strong?: boolean
  /** Per cell: `good` paints the number green, `bad` red. */
  tones?: Array<'good' | 'bad' | undefined>
}

/**
 * A table of figures: one header row, a label per row, numbers right-aligned. A real table, with a caption for screen readers;
 * on a narrow screen it scrolls inside its own box, never the page.
 */
export function FigureTable({ caption, columns, rows, tone = 'light' }: { caption: string; columns: ReactNode[]; rows: TableRow[]; tone?: 'light' | 'dark' }) {
  return (
    <div className={`land-table land-table--${tone}`} role="region" aria-label={caption} tabIndex={0}>
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column, i) => (
              <th key={i} scope="col">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={row.strong ? 'land-table__strong' : undefined}>
              <th scope="row">{row.label}</th>
              {row.cells.map((cell, j) => (
                <td key={j} className={row.tones?.[j] ? `land-table__${row.tones[j]}` : undefined}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
