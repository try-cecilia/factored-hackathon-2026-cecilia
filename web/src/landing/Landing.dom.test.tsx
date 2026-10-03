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
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Hola, soy Cecilia. El modelo elige la consulta. El código escribe la respuesta.')
    expect(screen.getByRole('banner')).toBeTruthy()
    expect(screen.getByRole('main')).toBeTruthy()
    expect(screen.getByRole('contentinfo')).toBeTruthy()
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    const expected = [
      'Línea base medida',
      'Cada pieza aprendida se midió contra un baseline. La que no aprendía nada, se descartó.',
      'Una consulta al modelo. Todo lo demás es código determinístico.',
      '548 casos offline y 138 en vivo. Cero inseguros, salvo 1 de Haiku 4.5.',
      'Sin controles, un modelo malo da 74,8% de resultados inseguros. Con todos, 0,0%.',
      'Más evidencia',
      'Lo que Cecilia no resuelve, lo decide una persona con el caso ya armado.',
      'Personas que no la construyeron la atacaron 83 minutos. Ninguno de los cinco fallos buscados apareció.',
      'Un tercio de centavo de dólar por resolución. Si el modelo se cae, sigue atendiendo.',
      'Un cero medido no es un cero garantizado.',
      'Cada cifra de esta página tiene un documento detrás, con su fecha y su n.',
      'Stack',
      'Seguridad · por dentro',
      'Probar como cliente. Resolver el caso como operador.',
    ]
    expect(titles).toEqual(expected)
  })

  it('links the header to sections that exist', () => {
    const { container } = renderWithI18n(<Landing />)
    const nav = screen.getByRole('navigation', { name: 'Secciones' })
    const targets = within(nav).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(targets).toEqual([`#${sections.architecture}`, `#${sections.data}`, `#${sections.results}`, `#${sections.security}`, `#${sections.evidence}`])
    const footer = within(screen.getByRole('navigation', { name: 'Documentación' })).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(footer).toEqual([`#${sections.limits}`, `#${sections.security}`, `#${sections.evidence}`])
    for (const target of [...targets, ...footer]) expect(container.querySelector(target as string)).toBeTruthy()
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
    expect(screen.getByText('Casos de Sonnet 5 cuyo resultado cambió entre corridas (1 de 138).')).toBeTruthy()
    expect(screen.getByText('Casos que mandaron un registro del cliente al modelo. En vivo: 0 de 138.')).toBeTruthy()
    expect(screen.getByText(/58\.234 movimientos pendientes en el dataset \(1,99%\)/)).toBeTruthy()
    expect(screen.getByText(/El 63,5% del baseline es una cota superior/)).toBeTruthy()
    expect(screen.getByText(/En vivo: 2 de octubre de 2026; la tabla muestra la corrida 1 de 3/)).toBeTruthy()
  })

  it('draws the results as real tables, each with a caption and its column headers', () => {
    renderWithI18n(<Landing />)
    const tables = screen.getAllByRole('table')
    expect(tables).toHaveLength(4)
    const [offline, live, ablation, queue] = tables
    expect(within(queue).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Tipo', 'Caso', 'Tiempo en espera', 'Objetivo'])
    expect(within(queue).getAllByRole('row').slice(1).map((tr) => tr.lastElementChild?.textContent)).toEqual(['15m', '2h', '4h'])
    expect(within(offline).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Offline · 548 casos', 'Bot de palabras', 'Modelo ideal', 'Adversarial'])
    expect(within(live).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['En vivo · muestra de 138 × 3 corridas', 'Sonnet 5 ★', 'Haiku 4.5'])
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

  it('marks the projection as one, the queue as a mock, and traces the big figures to their n and date', () => {
    renderWithI18n(<Landing />)
    expect(screen.getByText('No es una medición: aplica la tasa en vivo a los contactos reales.')).toBeTruthy()
    expect(screen.getByText(/^Maqueta con datos de ejemplo\. Los objetivos \(15 min, 2 h, 4 h\) son una propuesta para la demo/)).toBeTruthy()
    expect(screen.getByText('test n = 85 · ADR-006 · 01/10/2026')).toBeTruthy()
    expect(screen.getByText('57 de 60 en alcance · muestra de 138 · 02/10/2026')).toBeTruthy()
    expect(screen.getAllByText('Sonnet 5 · muestra de 138 casos · 02/10/2026')).toHaveLength(2)
    expect(screen.getByText(/^0 de 138 en vivo da una cota superior aproximada al 95% de ≈2,2%; 0 de 548 offline, de ≈0,55%\. Vale para este experimento/)).toBeTruthy()
  })

  it('says what each figure measures: its denominator, its exception, its sample and its caveat', () => {
    renderWithI18n(<Landing />)
    // Safe automated resolution is over the cases in scope, not the whole sample.
    expect(screen.getByText('resolución automática segura, 57 de 60 casos en alcance')).toBeTruthy()
    expect(screen.getByRole('rowheader', { name: 'Resolución automática segura (en alcance, n = 60)' })).toBeTruthy()
    expect(screen.getByRole('rowheader', { name: 'Resolución automática segura (en alcance, n = 238)' })).toBeTruthy()
    expect(screen.getByText(/se mide sobre los 60 casos dentro del alcance: 57 de 60, 95,0% \[86,3–98,3\]/)).toBeTruthy()
    // The guard that recalls 93,3% is the lexicon and the classifier together.
    expect(screen.getByText(/^La guarda combinada, léxico \+ clasificador, detectó el 93,3%/)).toBeTruthy()
    // The 234 cases are failure and regression cases, no longer held out.
    expect(screen.getByText(/^234 casos escritos por el equipo, ES y PT, offline\. Lo que encontraron se corrigió/)).toBeTruthy()
    // The data gate is about quarantined rows per table, and the run had warnings.
    expect(screen.getByText('Si más del 1% de las filas de una tabla queda en cuarentena, se revierte su carga.')).toBeTruthy()
    expect(screen.getByText('294 · 0 · 16')).toBeTruthy()
    // Freshness is off in the static demo; the fraud AUC is over a sample; the load row of the red team is not a load test.
    expect(screen.getByText(/Control de frescura configurable, apagado en la demo de datos estáticos/)).toBeTruthy()
    expect(screen.getByText('muestra: 4.316 fraudes + 300.000 legítimos · ADR-005')).toBeTruthy()
    expect(screen.getByText('Demo inutilizada por carga (máximo 2 chats simultáneos; no es una prueba de saturación)')).toBeTruthy()
    // Retries are per provider, with a fallback provider: no promise of a total maximum.
    expect(screen.getByText(/^Una consulta al modelo por turno, con hasta 2 intentos por proveedor y respaldo en otro proveedor,/)).toBeTruthy()
    expect(screen.getByText('1 · hasta 2 intentos por proveedor')).toBeTruthy()
    expect(screen.getByText(/Hasta 2 intentos por proveedor, con respaldo en otro\./)).toBeTruthy()
    // Offline latencies say which run they are.
    expect(screen.getByText(/‡ Corrida local del 2 de octubre de 2026: las latencias dependen de la máquina\./)).toBeTruthy()
    const offline = screen.getAllByRole('table')[0]
    const latency = within(offline).getByRole('rowheader', { name: /^Latencia sin LLM/ }).closest('tr') as HTMLElement
    expect(within(latency).getAllByRole('cell').map((td) => td.textContent)).toEqual(['4,1 / 13,3', '7,8 / 29,2', '7,0 / 23,1'])
  })

  it('draws the evidence and the limits without links while there is no public repository', () => {
    renderWithI18n(<Landing />)
    const grid = screen.getByRole('heading', { name: 'Evaluación del sistema' }).closest('ul') as HTMLElement
    expect(within(grid).getAllByRole('heading', { level: 3 })).toHaveLength(9)
    expect(within(grid).queryAllByRole('link')).toHaveLength(0)
    expect(screen.queryByRole('link', { name: /repositorio/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /lista completa de límites/ })).toBeNull()
  })

  it('gives every image a text alternative, empty only when it repeats what is next to it', () => {
    const { container } = renderWithI18n(<Landing />)
    for (const img of container.querySelectorAll('img')) expect(img.hasAttribute('alt')).toBe(true)
    expect(screen.getAllByRole('img', { name: 'Cecilia, la asistente de Cecilai' }).length).toBe(2)
  })

  it('speaks Portuguese with the same figures', () => {
    renderWithI18n(<Landing />, 'pt')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Olá, sou a Cecilia. O modelo escolhe a consulta. O código escreve a resposta.')
    expect(screen.getByRole('link', { name: /Entrar na demo/ })).toBeTruthy()
    expect(screen.getByText(/Ao vivo: 2 de outubro de 2026; a tabela mostra a rodada 1 de 3/)).toBeTruthy()
    expect(screen.getAllByText((_, el) => el?.textContent === '84,7%').length).toBeGreaterThan(0)
  })
})
