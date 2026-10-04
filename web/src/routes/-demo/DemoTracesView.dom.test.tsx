import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { DemoTrace } from '../../chat/types'
import { renderWithI18n } from '../../test/render'
import { DemoTracesView } from './DemoTracesView'

const trace = (n: number, sla: number | null): DemoTrace => ({
  trace_id: `TR-${n}`, transaction_id: `TXN-${n}`, queue: 'payments_ops', status: 'open', sla_business_days: sla, created_at: n,
})
const traces = [trace(0, 0), trace(1, 1), trace(3, 3), trace(9, null)]

describe('the demo bank traces page says every deadline in the visitor language, zero included, and never "open"', () => {
  it.each([
    ['es', 'Abierto', ['0 días hábiles', '1 día hábil', '3 días hábiles', 'Sin plazo respaldado']],
    ['pt', 'Aberto', ['0 dias úteis', '1 dia útil', '3 dias úteis', 'Sem prazo respaldado']],
  ] as const)('in %s, in the table and in the phone cards', (locale, open, deadlines) => {
    renderWithI18n(<DemoTracesView traces={traces} />, locale)
    const table = screen.getByRole('table')
    const cards = document.querySelector('.demo-traces__cards') as HTMLElement
    for (const view of [table, cards]) {
      const rows = traces.map((r) => (within(view).getByText(r.trace_id).closest(view === table ? 'tr' : 'li') as HTMLElement).textContent ?? '')
      rows.forEach((row, i) => {
        expect(row).toContain(deadlines[i])
        expect(row).toContain(open)
      })
      expect(view.textContent).not.toMatch(/\bopen\b|—/)
    }
  })
})
