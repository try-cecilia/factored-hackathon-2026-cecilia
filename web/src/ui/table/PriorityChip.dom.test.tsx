import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithI18n } from '../../test/render'
import { PriorityChip } from './PriorityChip'
import { priorityOf } from './priority'

describe('PriorityChip', () => {
  it.each([['es', 'Alta', 'Desconocida'], ['pt', 'Alta', 'Desconhecida']] as const)('says "unknown" for a case with no priority (%s)', (locale, high, unknown) => {
    renderWithI18n(<><PriorityChip priority={priorityOf('High')} /><PriorityChip priority={priorityOf(undefined)} /></>, locale)
    expect(screen.getByText(high)).toBeTruthy()
    expect(screen.getByText(unknown).className).toContain('ui-priority--unknown')
  })
})
