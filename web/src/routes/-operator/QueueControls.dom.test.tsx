import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithI18n } from '../../test/render'
import { FilterSelect, SearchBox } from './QueueControls'

describe('the form fields of the queue', () => {
  it('the search box has a stable id and name and keeps its accessible name', async () => {
    const onChange = vi.fn()
    renderWithI18n(<SearchBox value="" onChange={onChange} />)
    const box = screen.getByRole('searchbox', { name: 'Buscar casos' }) as HTMLInputElement
    expect(box.id).toBe('op-search')
    expect(box.name).toBe('q')
    await userEvent.setup().type(box, 'a')
    expect(onChange).toHaveBeenCalledWith('a')
  })

  it.each([
    ['es', 'prioridad', 'Prioridad'],
    ['es', 'pais', 'País'],
    ['pt', 'idioma', 'Idioma'],
    ['pt', 'prioridad', 'Prioridade'],
  ] as const)('a filter select has an id and a name of its own and keeps its name for assistive technology (%s, %s)', (locale, field, label) => {
    renderWithI18n(<FilterSelect field={field} name={label} value={undefined} onChange={() => {}} options={[{ value: 'x', label: 'X' }]} />, locale)
    const select = screen.getByRole('combobox', { name: label }) as HTMLSelectElement
    expect(select.id).toBe(`op-filter-${field}`)
    expect(select.name).toBe(field)
  })

  it('a chosen option is reported, and the empty one clears the filter', async () => {
    const onChange = vi.fn()
    renderWithI18n(<FilterSelect field="idioma" name="Idioma" value="es" onChange={onChange} options={[{ value: 'es', label: 'ES' }, { value: 'pt', label: 'PT' }]} />)
    const user = userEvent.setup()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Idioma' }), 'pt')
    expect(onChange).toHaveBeenLastCalledWith('pt')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Idioma' }), '')
    expect(onChange).toHaveBeenLastCalledWith(undefined)
  })
})
