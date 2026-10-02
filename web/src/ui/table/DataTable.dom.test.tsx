import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { replaceEqualDeep } from '@tanstack/react-router'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/context'
import { dictionaries, renderWithI18n } from '../../test/render'
import { DataTable } from './DataTable'
import { StatusIndicator } from './PriorityChip'
import type { Column } from './types'

type Row = { id: string; name: string }
const rows: Row[] = [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }]
const columns: Column<Row>[] = [{ id: 'name', header: 'Name', rowHeader: true, cell: (r) => r.name }]

describe('DataTable, the row whose detail is open', () => {
  it('is marked as current without becoming a selection', () => {
    renderWithI18n(<DataTable rows={rows} columns={columns} getRowId={(r) => r.id} caption="Cases" density="compact" onRowClick={() => {}} activeRowId="b" />)
    const [alpha, beta] = screen.getAllByRole('row').slice(1)
    expect(alpha.getAttribute('aria-current')).toBeNull()
    expect(beta.getAttribute('aria-current')).toBe('true')
    expect(beta.hasAttribute('data-selected')).toBe(true)
    expect(screen.queryByRole('checkbox')).toBeNull()
  })

  it('opens a row with the keyboard as with the pointer', async () => {
    const open = vi.fn()
    renderWithI18n(<DataTable rows={rows} columns={columns} getRowId={(r) => r.id} caption="Cases" onRowClick={open} />)
    const user = userEvent.setup()
    await user.click(screen.getByText('Alpha'))
    screen.getAllByRole('row')[2].focus()
    await user.keyboard('{Enter}')
    expect(open.mock.calls.map(([row]) => row.id)).toEqual(['a', 'b'])
  })
})

describe('DataTable, the cells', () => {
  it('name their column, so a narrow layout can place each one (the queue is drawn as cards on a phone)', () => {
    const two: Column<Row>[] = [...columns, { id: 'size', header: 'Size', cell: (r) => r.name.length }]
    const { container } = renderWithI18n(<DataTable rows={rows} columns={two} getRowId={(r) => r.id} caption="Cases" />)
    const cells = [...container.querySelectorAll('tbody tr:first-child > *')]
    expect(cells.map((cell) => cell.getAttribute('data-col'))).toEqual(['name', 'size'])
    expect(cells[0].tagName).toBe('TH')
  })
})

describe('StatusIndicator', () => {
  it('draws the danger tone with its label, so color is never the only signal', () => {
    const { container } = renderWithI18n(<StatusIndicator tone="danger">Rechazado</StatusIndicator>)
    expect(container.querySelector('.ui-status__dot--danger')).not.toBeNull()
    expect(screen.getByText('Rechazado')).toBeTruthy()
  })
})

describe('DataTable, a refresh', () => {
  const inI18n = (ui: ReactElement) => <I18nProvider locale="es" messages={dictionaries.es}>{ui}</I18nProvider>

  it('with an identical snapshot runs no cell again; a changed row runs only its own; new columns (a new age) run them all', () => {
    const cell = vi.fn((r: Row) => r.name)
    const counted: Column<Row>[] = [{ id: 'name', header: 'Name', rowHeader: true, cell }]
    const open = () => {}
    const table = (data: readonly Row[], cols = counted) => <DataTable rows={data} columns={cols} getRowId={(r) => r.id} caption="Cases" density="compact" onRowClick={open} />
    const first = [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }]
    const { rerender } = renderWithI18n(table(first))
    expect(cell).toHaveBeenCalledTimes(2)

    // The router's structural sharing: the same JSON again gives back the objects already on screen.
    const same = replaceEqualDeep(first, JSON.parse(JSON.stringify(first)) as Row[])
    expect(same).toBe(first)
    rerender(inI18n(table([...same])))
    expect(cell).toHaveBeenCalledTimes(2)

    const changed = replaceEqualDeep(first, [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta 2' }])
    expect(changed[0]).toBe(first[0])
    rerender(inI18n(table(changed)))
    expect(cell).toHaveBeenCalledTimes(3)
    expect(screen.getByText('Beta 2')).toBeTruthy()

    rerender(inI18n(table(changed, [...counted])))
    expect(cell).toHaveBeenCalledTimes(5)
  })
})
