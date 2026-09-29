import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithI18n } from '../../test/render'
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

describe('StatusIndicator', () => {
  it('draws the danger tone with its label, so color is never the only signal', () => {
    const { container } = renderWithI18n(<StatusIndicator tone="danger">Rechazado</StatusIndicator>)
    expect(container.querySelector('.ui-status__dot--danger')).not.toBeNull()
    expect(screen.getByText('Rechazado')).toBeTruthy()
  })
})
