import { createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet, RouterProvider, type AnyRouter } from '@tanstack/react-router'
import { act, render, screen } from '@testing-library/react'
import { useMemo } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMinute } from '../routes/-operator/now'
import { dictionaries } from '../test/render'
import { DataTable } from '../ui/table/DataTable'
import type { Column } from '../ui/table/types'
import { useT } from './context'
import type { Locale } from './locales'
import { RootI18n } from './root'

type Row = { id: string; at: number }
const rows: Row[] = [{ id: 'a', at: 0 }]
const cell = vi.fn()

// A page built like the queue: columns memoized on the translator and on the minute the ages are counted from.
function Page() {
  const t = useT()
  const minute = useMinute()
  const columns = useMemo<Column<Row>[]>(
    () => [{ id: 'status', header: t('operator.queue.columns.status'), cell: (r) => (cell(), `${t('operator.status.open')} ${r.id} ${minute}`) }],
    [t, minute],
  )
  return <DataTable rows={rows} columns={columns} getRowId={(r) => r.id} caption="Cola" density="compact" />
}

/** The real router, in memory, whose root loader answers every run with a new copy of the dictionary, as the server does. */
function mount() {
  let locale: Locale = 'es'
  const root = createRootRoute({
    loader: () => ({ locale, messages: structuredClone(dictionaries[locale]) }),
    component: () => <RootI18n><Outlet /></RootI18n>,
  })
  const page = createRoute({ getParentRoute: () => root, path: '/', component: Page })
  const router = createRouter({ routeTree: root.addChildren([page]), history: createMemoryHistory({ initialEntries: ['/'] }) }) as AnyRouter
  render(<RouterProvider router={router} />)
  return { router, setLocale: (next: Locale) => { locale = next } }
}

afterEach(() => vi.useRealTimers())

describe('the root dictionary across router.invalidate()', () => {
  it('a reload of every loader that brings the same texts keeps the translator: no cell runs again', async () => {
    const { router } = mount()
    expect(await screen.findByText(/^Abierto a /)).toBeTruthy()
    const before = cell.mock.calls.length
    await act(() => router.invalidate())
    await act(() => router.invalidate())
    expect(cell.mock.calls.length).toBe(before)
  })

  it('a change of language does reach the cells', async () => {
    const { router, setLocale } = mount()
    await screen.findByText(/^Abierto a /)
    setLocale('pt')
    await act(() => router.invalidate())
    expect(await screen.findByText(/^Aberto a /)).toBeTruthy()
  })

  it('and so does the minute the ages are counted from', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mount()
    const first = (await screen.findByText(/^Abierto a /)).textContent
    const before = cell.mock.calls.length
    await act(() => vi.advanceTimersByTimeAsync(61_000))
    expect(cell.mock.calls.length).toBeGreaterThan(before)
    expect(screen.getByText(/^Abierto a /).textContent).not.toBe(first)
  })
})
