import { cleanup, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithI18n } from '../test/render'
import { figures as F, formatFigure } from './figures'
import { Landing } from './Landing'
import { consoleEntry, demoEntry, sections, signInEntry } from './links'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...rest }: { to: string; children?: ReactNode }) => <a href={to} {...rest}>{children}</a>,
  useRouter: () => ({ invalidate: async () => {} }),
}))
vi.mock('../server/locale.functions', () => ({ setLocale: vi.fn() }))

afterEach(cleanup)

const es = (figure: (typeof F)[keyof typeof F]) => formatFigure(figure, 'es')

describe('the landing', () => {
  it('has one h1, the landmarks and every section of the design, in order', () => {
    renderWithI18n(<Landing />)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('El modelo elige la consulta. El código escribe la respuesta.')
    expect(screen.getByRole('banner')).toBeTruthy()
    expect(screen.getByRole('main')).toBeTruthy()
    expect(screen.getByRole('contentinfo')).toBeTruthy()
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    const expected = [
      'Línea base medida',
      'Cada pieza aprendida se midió contra un baseline. La que no aprendía nada, se descartó.',
      'Una llamada al modelo. Todo lo demás es código determinístico.',
      '548 casos offline y 138 en vivo. Cero resultados inseguros.',
      'Sin controles, un modelo malo da 74,8% de resultados inseguros. Con todos, 0,0%.',
      'Más evidencia',
      'Stack',
      'Seguridad · OWASP ASVS 4.0.3 nivel 1',
      'Probala como cliente. Resolvé su caso como operador.',
    ]
    expect(titles).toEqual(expected)
  })

  it('links the header to sections that exist', () => {
    const { container } = renderWithI18n(<Landing />)
    const nav = screen.getByRole('navigation', { name: 'Secciones' })
    const targets = within(nav).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(targets).toEqual([`#${sections.architecture}`, `#${sections.data}`, `#${sections.results}`])
    for (const target of targets) expect(container.querySelector(target as string)).toBeTruthy()
  })

  it('shows the figures of figures.ts, in the notation of the language', () => {
    renderWithI18n(<Landing />)
    const strip = screen.getByRole('list', { name: 'Cifras principales' })
    expect(within(strip).getAllByRole('listitem').map((li) => li.querySelector('strong')?.textContent)).toEqual([
      `0/${es(F.offlineCases)}`,
      `0/${es(F.liveCases)}`,
      `${es(F.sonnetSafe)}%`,
      `${es(F.sonnetP50)} s`,
    ])
    for (const text of ['4,4 M', '84,7%', '0,506', '+8,2 a +34,1', '0,0029', '4.316', '150.000']) {
      expect(screen.getAllByText((_, el) => el?.textContent === text).length, text).toBeGreaterThan(0)
    }
    expect(screen.getByText(/58\.234 movimientos pendientes en el dataset \(1,99%\)/)).toBeTruthy()
    expect(screen.getByText(/es una cota superior/)).toBeTruthy()
    expect(screen.getByText(/En vivo: 2 de octubre de 2026\./)).toBeTruthy()
  })

  it('draws the results as real tables, each with a caption and its column headers', () => {
    renderWithI18n(<Landing />)
    const tables = screen.getAllByRole('table')
    expect(tables).toHaveLength(3)
    const [offline, live, ablation] = tables
    expect(within(offline).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Offline · 548 casos', 'Bot de palabras', 'Modelo ideal', 'Adversarial'])
    expect(within(live).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['En vivo · 138 casos × 3 corridas', 'Sonnet 5 ★', 'Haiku 4.5'])
    const unsafe = within(offline).getByRole('rowheader', { name: 'Resultados inseguros' }).closest('tr') as HTMLElement
    expect(within(unsafe).getAllByRole('cell').map((td) => td.textContent)).toEqual(['0/548', '0/548', '0/548'])
    const runs = within(live).getByRole('rowheader', { name: 'Inseguros por corrida' }).closest('tr') as HTMLElement
    expect(within(runs).getAllByRole('cell').map((td) => td.textContent)).toEqual(['0 · 0 · 0', '0 · 1 · 0'])
    expect(within(ablation).getAllByRole('cell').map((td) => td.textContent)).toEqual(['17,5%', '74,8%', '13,1%', '49,3%', '8,8%', '8,8%', '0,0%', '0,0%'])
    for (const table of tables) expect(table.querySelector('caption')?.textContent).toBeTruthy()
  })

  it('takes the visitor to the demo, the sign-in and the console, and never to the private repository', () => {
    renderWithI18n(<Landing />)
    expect(screen.getByRole('link', { name: /Probar la demo/ }).getAttribute('href')).toBe(demoEntry.to)
    expect(screen.getByRole('link', { name: /Entrar a la demo/ }).getAttribute('href')).toBe(demoEntry.to)
    expect(screen.getByRole('link', { name: 'Ingresar con PIN' }).getAttribute('href')).toBe(signInEntry.to)
    expect(screen.getByRole('link', { name: 'Consola con clave' }).getAttribute('href')).toBe(consoleEntry.to)
    expect(screen.getByRole('link', { name: 'Ver la evaluación' }).getAttribute('href')).toBe(`#${sections.results}`)
    for (const link of screen.getAllByRole('link')) expect(link.getAttribute('href') ?? '').not.toMatch(/github\.com/)
  })

  it('gives every image a text alternative, empty only when it repeats what is next to it', () => {
    const { container } = renderWithI18n(<Landing />)
    for (const img of container.querySelectorAll('img')) expect(img.hasAttribute('alt')).toBe(true)
    expect(screen.getAllByRole('img', { name: 'Cecilia, la asistente de Cecilai' }).length).toBe(2)
  })

  it('speaks Portuguese with the same figures', () => {
    renderWithI18n(<Landing />, 'pt')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('O modelo escolhe a consulta. O código escreve a resposta.')
    expect(screen.getByRole('link', { name: /Entrar na demo/ })).toBeTruthy()
    expect(screen.getByText(/Ao vivo: 2 de outubro de 2026\./)).toBeTruthy()
    expect(screen.getAllByText((_, el) => el?.textContent === '84,7%').length).toBeGreaterThan(0)
  })
})
