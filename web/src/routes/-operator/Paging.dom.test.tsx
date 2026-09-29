import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { I18nProvider } from '../../i18n/context'
import { renderWithI18n } from '../../test/render'
import { DataTable } from '../../ui'
import { pageSlice } from './queue'

const columns = [{ id: 'n', header: 'N', rowHeader: true, cell: (r: number) => `caso ${r}` }]
const Table = ({ rows, page }: { rows: number[]; page: number }) => {
  const shown = pageSlice(rows, page, 25)
  return <DataTable density="compact" caption="Cola" rows={shown.rows} columns={columns} getRowId={String} pagination={{ page: shown.page, pageSize: 25, total: rows.length, onPageChange: () => {} }} />
}
const numbers = (n: number) => Array.from({ length: n }, (_, i) => i)

describe('the queue table when a refresh leaves fewer pages than the one being read', () => {
  it('shows the last page with its rows, the same one the pager says', () => {
    const { rerender } = renderWithI18n(<Table rows={numbers(26)} page={2} />)
    expect(screen.getByText('Mostrando 26–26 de 26')).toBeTruthy()
    expect(screen.getAllByRole('row')).toHaveLength(2)
    rerender(<I18nProvider locale="es"><Table rows={numbers(25)} page={2} /></I18nProvider>)
    expect(screen.getByText('Mostrando 1–25 de 25')).toBeTruthy()
    expect(screen.getAllByRole('row')).toHaveLength(26)
  })
})
