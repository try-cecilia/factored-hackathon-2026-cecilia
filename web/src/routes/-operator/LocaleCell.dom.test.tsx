import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { QueueRow } from '../../server/queue-row'
import { renderWithI18n } from '../../test/render'
import { LocaleCell } from './ui'

const row = (over: Partial<QueueRow>): QueueRow => ({
  ticket_id: 't1', created_at: 1, category: 'fraud', priority: 'High', queue: 'fraud_ops', customer_id: 'C-1', country: 'México', language: 'es', request: 'r',
  desk: { status: 'open', operator: null, version: 0 }, ...over,
})

describe('LocaleCell', () => {
  it('shows country and language when both are there', () => {
    renderWithI18n(<LocaleCell row={row({})} />)
    expect(screen.getByText('MX·ES')).toBeTruthy()
  })

  it.each([
    ['es', 'MX·Desconocido'],
    ['pt', 'MX·Desconhecido'],
  ] as const)('a case without language keeps the short mark visible and says the word to assistive technology (%s)', (locale, full) => {
    for (const language of [undefined, null, ''] as const) {
      const { container, unmount } = renderWithI18n(<LocaleCell row={row({ language })} />, locale)
      expect(screen.getAllByText(full)).toHaveLength(1) // the words are read once
      expect(screen.getByText(full).className).toContain('sr-only') // by text: what a screen reader reads
      const mark = container.querySelector('[aria-hidden="true"]')
      expect(mark?.textContent).toBe('MX·?')
      // The title is on the hidden mark: on the element a screen reader reads it would be described a second time.
      expect(container.querySelectorAll('[title]')).toHaveLength(1)
      expect(container.querySelector('[title]')).toBe(mark)
      expect(mark?.getAttribute('title')).toBe(full)
      unmount()
    }
  })
})
