import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/context'
import { dictionaries } from '../../test/render'
import type { DeskStatus, Result, Ticket } from '../../server/operator.functions'
import { readAgain, guarded } from './reload'
import { TicketRoute } from './TicketRoute'
import { Unavailable } from './Unavailable'

const NOW = Date.now() / 1000
function ticket(id: string, status: DeskStatus, version: number, history: Ticket['desk']['history'] = []): Ticket {
  return {
    ticket_id: id, trace_id: null, created_at: NOW - 600, category: 'trace_review', priority: 'High', queue: 'payments_ops', customer_id: 'C-1', session_ref: 'sess-1',
    segment: 'Retail', country: 'México', language: 'es', request: 'Rastrear el pago.', prior_requests: [], reason: 'r', policy_rule: 'trace_review', verified_facts: [],
    evidence: [], actions_taken: [], open_questions: [], suggested_next_step: 's', pending_action: { tool: 'request_trace', transaction_id: 'tx1', product_id: 'p1' },
    desk: { ticket_id: id, status, operator: status === 'open' ? null : 'ana.ruiz', trace_id: null, version, history },
  }
}
const released = [{ action: 'release', status: 'handed_back', operator: 'diego.m', ts: NOW - 60, detail: {} }]
const ID = 'a91f3c00'
const view = { canAct: true, operator: 'ana.ruiz' }

/** The real router, in memory, with a route that reads the case the way the console's route does. */
function mount(read: () => Promise<Result<Ticket>>, { guard = true } = {}) {
  const act = vi.fn(async () => ({ ok: false as const, status: 409, message: 'the ticket changed' }))
  const root = createRootRoute()
  const route = createRoute({
    getParentRoute: () => root,
    path: '/cola/$ticketId',
    loader: () => (guard ? guarded(read) : read()),
    component: function Page() {
      const result = route.useLoaderData() as Result<Ticket>
      const { ticketId } = route.useParams()
      return <TicketRoute from="/cola/$ticketId" result={result} ticketId={ticketId} view={view} act={act} />
    },
  })
  const router = createRouter({ routeTree: root.addChildren([route]), history: createMemoryHistory({ initialEntries: [`/cola/${ID}`] }) })
  render(<I18nProvider locale="es" messages={dictionaries.es}><RouterProvider router={router} /></I18nProvider>)
  return { router, act }
}

const flush = async () => new Promise((r) => setTimeout(r, 0))

describe('reading the case again with the real router', () => {
  it('keeps the 409 lock, and the panel, when the transport fails during "Recargar caso"', async () => {
    const read = vi.fn<() => Promise<Result<Ticket>>>()
      .mockResolvedValueOnce({ ok: true, data: ticket(ID, 'claimed', 3) }) // first paint
      .mockResolvedValueOnce({ ok: true, data: ticket(ID, 'open', 4, released) }) // after the refused action
      .mockRejectedValueOnce(new Error('fetch failed')) // "Recargar caso": the browser cannot reach the BFF
    const { router } = mount(read)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Aprobar rastreo/ }))
    await screen.findByText('No se aplicó: el caso cambió')

    await user.click(screen.getByRole('button', { name: /Recargar caso/ }))
    await screen.findByText('No se pudo recargar el caso')
    expect(screen.getByText('No se aplicó: el caso cambió')).toBeTruthy()
    expect((screen.getByRole('button', { name: /Tomar caso/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(router.state.matches.at(-1)?.status).toBe('success') // the failure came back as a result, not as a route error

    // And when the network is back, that reload does lift it.
    read.mockResolvedValueOnce({ ok: true, data: ticket(ID, 'open', 4, released) })
    await user.click(screen.getByRole('button', { name: /Recargar caso/ }))
    await waitFor(() => expect(screen.queryByText('No se aplicó: el caso cambió')).toBeNull())
  })

  it('a loader that throws leaves the match in error with the old data: that is not a successful reload', async () => {
    const read = vi.fn<() => Promise<Result<Ticket>>>().mockResolvedValueOnce({ ok: true, data: ticket(ID, 'claimed', 3) }).mockRejectedValueOnce(new Error('fetch failed'))
    const { router } = mount(read, { guard: false })
    await screen.findByRole('button', { name: /Aprobar rastreo/ })
    expect(await readAgain(router, '/cola/$ticketId', ID, 3)).toBe(false)
    expect(router.state.matches.at(-1)?.status).toBe('error')
    await flush()
  })

  it('the data must be the case asked for and not older than the version on screen', async () => {
    const read = vi.fn<() => Promise<Result<Ticket>>>().mockResolvedValue({ ok: true, data: ticket(ID, 'open', 4, released) })
    const { router } = mount(read)
    await screen.findByText('Rastrear el pago.')
    expect(await readAgain(router, '/cola/$ticketId', ID, 4)).toBe(true)
    expect(await readAgain(router, '/cola/$ticketId', ID, 3)).toBe(true)
    expect(await readAgain(router, '/cola/$ticketId', ID, 5)).toBe(false) // the server is behind what the operator already saw
    expect(await readAgain(router, '/cola/$ticketId', 'another-case', 0)).toBe(false)
    read.mockResolvedValue({ ok: false, status: 503 })
    expect(await readAgain(router, '/cola/$ticketId', ID, 4)).toBe(false)
  })
})

/** The console's own shape: a layout with a beforeLoad that asks the BFF who is signed in, and the case as its child. */
function mountWithLayout(read: () => Promise<Result<Ticket>>, whoAmI: () => Promise<void>) {
  const act = vi.fn(async () => ({ ok: false as const, status: 409, message: 'the ticket changed' }))
  const root = createRootRoute()
  const layout = createRoute({
    getParentRoute: () => root,
    id: '_operator',
    beforeLoad: async () => {
      await whoAmI()
      return { view }
    },
    errorComponent: Unavailable,
  })
  const route = createRoute({
    getParentRoute: () => layout,
    path: '/cola/$ticketId',
    loader: () => guarded(read),
    component: function Page() {
      const result = route.useLoaderData() as Result<Ticket>
      const { ticketId } = route.useParams()
      return <TicketRoute from="/_operator/cola/$ticketId" result={result} ticketId={ticketId} view={view} act={act} />
    },
  })
  const router = createRouter({ routeTree: root.addChildren([layout.addChildren([route])]), history: createMemoryHistory({ initialEntries: [`/cola/${ID}`] }) })
  render(<I18nProvider locale="es" messages={dictionaries.es}><RouterProvider router={router} /></I18nProvider>)
  return { router }
}

describe('when the layout of the console fails while the case is read again', () => {
  const claimed = { ok: true as const, data: ticket(ID, 'claimed', 3) }
  const moved = { ok: true as const, data: ticket(ID, 'open', 4, released) }

  it('a failing parent makes the reload fail even though the child match kept its old data', async () => {
    const whoAmI = vi.fn<() => Promise<void>>().mockResolvedValueOnce().mockRejectedValueOnce(new Error('fetch failed'))
    const { router } = mountWithLayout(vi.fn().mockResolvedValue(moved), whoAmI)
    await screen.findByText('Rastrear el pago.')
    expect(await readAgain(router, '/_operator/cola/$ticketId', ID, 4)).toBe(false)
    expect(router.state.matches.map((m) => m.status)).toContain('error')
  })

  it('the 409 lock is still there when the console comes back', async () => {
    const read = vi.fn<() => Promise<Result<Ticket>>>().mockResolvedValueOnce(claimed).mockResolvedValue(moved)
    // 1st: first paint. 2nd: the refresh after the refused action. 3rd: "Recargar caso", which the layout fails.
    const whoAmI = vi.fn<() => Promise<void>>().mockResolvedValueOnce().mockResolvedValueOnce().mockRejectedValueOnce(new Error('fetch failed')).mockResolvedValue()
    mountWithLayout(read, whoAmI)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Aprobar rastreo/ }))
    await screen.findByText('No se aplicó: el caso cambió')

    await user.click(screen.getByRole('button', { name: /Recargar caso/ }))
    // The whole console is replaced by the error: the panel is gone, and so is its local state.
    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))
    await screen.findByText('No se aplicó: el caso cambió')
    expect((screen.getByRole('button', { name: /Tomar caso/ }) as HTMLButtonElement).disabled).toBe(true)

    // Only a complete, successful reload lifts it.
    await user.click(screen.getByRole('button', { name: /Recargar caso/ }))
    await waitFor(() => expect(screen.queryByText('No se aplicó: el caso cambió')).toBeNull())
  })
})
