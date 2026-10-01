import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { QueueRow } from '../../server/queue-row'
import { renderWithI18n } from '../../test/render'
import { AgeCell } from './AgeCell'

const NOW = Date.UTC(2026, 8, 29, 12, 0, 0)
const waited = (minutes: number) => (NOW - minutes * 60_000) / 1000
const row = (over: Partial<QueueRow> & { status?: QueueRow['desk']['status'] } = {}): QueueRow => {
  const { status = 'open', ...rest } = over
  return { ticket_id: 't1', created_at: waited(5), category: 'fraud', priority: 'High', queue: 'fraud_ops', customer_id: 'C-1', country: 'México', language: 'es', request: 'r', desk: { status, operator: null, version: 0 }, ...rest }
}

describe('AgeCell', () => {
  it('shows only the age of a case still within its objective', () => {
    const { container } = renderWithI18n(<AgeCell row={row()} now={NOW} locale="es" />)
    expect(screen.getByText('5m')).toBeTruthy()
    expect(container.querySelector('[data-overdue]')).toBeNull()
  })

  it.each([
    ['es', 'Vencido: el objetivo de atención era 15m'],
    ['pt', 'Vencido: a meta de atendimento era 15m'],
  ] as const)('marks a case past its objective, with words for assistive technology and read once (%s)', (locale, words) => {
    const { container } = renderWithI18n(<AgeCell row={row({ created_at: waited(40) })} now={NOW} locale={locale} />, locale)
    const mark = container.querySelector('[data-overdue]')
    expect(mark).toBeTruthy()
    expect(screen.getAllByText(`40m. ${words}`)).toHaveLength(1)
    expect(screen.getByText(`40m. ${words}`).className).toContain('sr-only')
    expect(container.querySelectorAll('[title]')).toHaveLength(1)
    expect(container.querySelector('[title]')?.getAttribute('aria-hidden')).toBe('true')
  })

  it('does not mark a taken case, however long ago it was filed', () => {
    const { container } = renderWithI18n(<AgeCell row={row({ created_at: waited(900), status: 'claimed' })} now={NOW} locale="es" />)
    expect(container.querySelector('[data-overdue]')).toBeNull()
    expect(screen.getByText('15h')).toBeTruthy()
  })
})
