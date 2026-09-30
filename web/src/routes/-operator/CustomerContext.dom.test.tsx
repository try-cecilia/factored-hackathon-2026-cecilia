import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CustomerContext } from '../../server/customer-context'
import type { Result } from '../../server/operator.functions'
import { I18nProvider } from '../../i18n/context'
import { dictionaries, renderWithI18n } from '../../test/render'
import { CustomerContextSection, CustomerContextView } from './CustomerContext'

const NOW = Date.now() / 1000
const data = (over: Partial<CustomerContext> = {}): CustomerContext => ({
  warehouse: { available: true, as_of: '2026-06-01' },
  products: [
    { product_id: 'PRD-1', type: 'Cuenta Ahorro', currency: 'USD', status: 'Active', last4: '0001' },
    { product_id: 'PRD-2', type: 'Tarjeta Crédito', currency: 'USD', status: 'Blocked', last4: '0004' },
  ],
  movements: [
    { transaction_id: 'TXN-9', date: '2026-05-30T10:00:00', product_id: 'PRD-1', type: 'Transfer', amount: 40, currency: 'USD', merchant: null, status: 'Pending', pending: true },
    { transaction_id: 'TXN-8', date: '2026-05-29T09:00:00', product_id: 'PRD-2', type: 'Purchase', amount: 12.5, currency: 'USD', merchant: 'Mercado Fixture', status: 'Approved', pending: false },
    { transaction_id: 'TXN-7', date: '2026-05-28T09:00:00', product_id: 'PRD-2', type: 'Purchase', amount: 3, currency: 'USD', merchant: 'Kiosco', status: 'Declined', pending: false },
  ],
  pending_omitted: 0,
  cases: [{ ticket_id: 'a91f3c00-1111', category: 'fraud', queue: 'fraud_ops', priority: 'High', created_at: NOW - 86400, status: 'claimed' }],
  traces: [{ trace_id: 'TR-ABCDEF0123456789', transaction_id: 'TXN-9', status: 'open', created_at: NOW - 3600 }],
  ...over,
})
const ok = (over?: Partial<CustomerContext>): Result<CustomerContext> => ({ ok: true, data: data(over) })

describe('the customer context of a case', () => {
  it('shows the products by type with the last four digits only, and never a number that is longer', () => {
    renderWithI18n(<CustomerContextView result={ok()} />)
    expect(screen.getByText('Cuenta de ahorro')).toBeTruthy()
    expect(screen.getByText('Tarjeta de crédito')).toBeTruthy()
    expect(screen.getByText('•••• 0001')).toBeTruthy()
    expect(screen.getByText('Terminada en 0001').className).toContain('sr-only') // read once: the dots are hidden from a screen reader
    expect(screen.getByText('•••• 0001').getAttribute('aria-hidden')).toBe('true')
    expect(screen.getByText('Bloqueado')).toBeTruthy()
    for (const product of screen.getAllByRole('listitem').slice(0, 2)) expect(product.textContent).not.toMatch(/\d{5,}/)
  })

  it('highlights the pending movement and says it in words, and marks a declined one', () => {
    const { container } = renderWithI18n(<CustomerContextView result={ok()} />)
    const rows = within(screen.getByRole('table', { name: 'Últimos movimientos' })).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(rows[0].hasAttribute('data-pending')).toBe(true)
    expect(rows[0].textContent).toContain('Transferencia')
    expect(rows[0].textContent).toContain('Pendiente')
    expect(rows[0].textContent).toContain('40.00 USD')
    expect(rows[1].hasAttribute('data-pending')).toBe(false)
    expect(rows[1].textContent).toContain('Compra · Mercado Fixture')
    expect(rows[1].textContent).not.toContain('Aprobado') // approved is the plain state: not repeated on every row
    expect(rows[2].textContent).toContain('Rechazado')
    expect(container.textContent).toContain('1 pendiente(s)')
  })

  it('says how many pending movements the list leaves out, and nothing when it leaves none', () => {
    const view = renderWithI18n(<CustomerContextView result={ok()} />)
    expect(screen.queryByText(/pendiente\(s\) más/)).toBeNull()
    view.rerender(<I18nProvider locale="es" messages={dictionaries.es}><CustomerContextView result={ok({ pending_omitted: 7 })} /></I18nProvider>)
    expect(screen.getByText('y 7 pendiente(s) más')).toBeTruthy()
    view.rerender(<I18nProvider locale="pt" messages={dictionaries.pt}><CustomerContextView result={ok({ pending_omitted: 7 })} /></I18nProvider>)
    expect(screen.getByText('e mais 7 pendente(s)')).toBeTruthy()
  })

  it('lists the other cases with a link to each and the rastreos of the customer', () => {
    renderWithI18n(<CustomerContextView result={ok()} caseLink={(id, label) => <a href={`/operador/cola/${id}`}>{label}</a>} />)
    const link = screen.getByRole('link', { name: 'a91f3c00' })
    expect(link.getAttribute('href')).toBe('/operador/cola/a91f3c00-1111')
    expect(screen.getByText(/Fraude/)).toBeTruthy()
    expect(screen.getByText('Tomado')).toBeTruthy()
    expect(screen.getByText('TR-ABCDEF0123456789')).toBeTruthy()
    expect(screen.getByText(/Movimiento TXN-9 · Abierto/)).toBeTruthy()
  })

  it('says there are none, section by section', () => {
    renderWithI18n(<CustomerContextView result={ok({ products: [], movements: [], cases: [], traces: [] })} />)
    for (const text of ['Sin productos.', 'Sin movimientos.', 'Ningún otro caso.', 'Ningún rastreo.']) expect(screen.getByText(text)).toBeTruthy()
  })

  it('speaks Portuguese to a Portuguese operator, with the warehouse words translated', () => {
    renderWithI18n(<CustomerContextView result={ok()} />, 'pt')
    expect(screen.getByText('Contexto do cliente')).toBeTruthy()
    expect(screen.getByText('Conta poupança')).toBeTruthy()
    expect(screen.getByText('Final 0001').className).toContain('sr-only')
    expect(screen.getByText('Transferência')).toBeTruthy()
    expect(screen.getByText('Recusada')).toBeTruthy()
  })

  it('a value the console does not know is shown as it came', () => {
    renderWithI18n(<CustomerContextView result={ok({ products: [{ product_id: 'P', type: 'Fideicomiso', currency: 'ARS', status: 'Dormant', last4: null }] })} />)
    expect(screen.getByText('Fideicomiso')).toBeTruthy()
    expect(screen.getByText('Dormant')).toBeTruthy()
    expect(screen.getByText('••••')).toBeTruthy()
  })

  it('a warehouse that is down says so, and the cases and rastreos are still there', () => {
    renderWithI18n(<CustomerContextView result={ok({ warehouse: { available: false, as_of: null }, products: [], movements: [] })} />)
    expect(screen.getByText('Los productos y movimientos del cliente no están disponibles ahora.')).toBeTruthy()
    expect(screen.queryByText('Sin productos.')).toBeNull()
    expect(screen.getByText('TR-ABCDEF0123456789')).toBeTruthy()
    expect(screen.getByText('Tomado')).toBeTruthy()
  })
})

describe('reading it', () => {
  it('shows that it is loading, then the context; the case itself never waits for it', async () => {
    let finish!: (r: Result<CustomerContext>) => void
    const load = vi.fn(() => new Promise<Result<CustomerContext>>((done) => (finish = done)))
    renderWithI18n(<CustomerContextSection ticketId="t1" load={load} />)
    expect(screen.getByText('Cargando el contexto del cliente')).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Contexto del cliente' }).getAttribute('aria-busy')).toBe('true')
    finish(ok())
    await screen.findByText('Cuenta de ahorro')
    expect(screen.getByRole('region', { name: 'Contexto del cliente' }).hasAttribute('aria-busy')).toBe(false)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('a failed read says the context is not available, that the rest of the case works, and can be tried again', async () => {
    const load = vi.fn<(id: string) => Promise<Result<CustomerContext>>>()
    load.mockResolvedValueOnce({ ok: false, status: 503 }).mockResolvedValueOnce(ok())
    renderWithI18n(<CustomerContextSection ticketId="t1" load={load} />)
    await screen.findByText('El contexto del cliente no está disponible ahora. El resto del caso funciona igual.')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByText('Cuenta de ahorro')
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('an expired session says so instead of offering to try again', async () => {
    renderWithI18n(<CustomerContextSection ticketId="t1" load={async () => ({ ok: false, status: 401 })} />)
    await screen.findByText(/La sesión venció/)
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('an answer that arrives late for the previous case is not shown on the next one', async () => {
    const answers: Record<string, (r: Result<CustomerContext>) => void> = {}
    const load = (id: string) => new Promise<Result<CustomerContext>>((done) => (answers[id] = done))
    const view = renderWithI18n(<CustomerContextSection ticketId="one" load={load} />)
    view.rerender(<I18nProvider locale="es" messages={dictionaries.es}><CustomerContextSection ticketId="two" load={load} /></I18nProvider>)
    answers.one(ok({ products: [{ product_id: 'X', type: 'Seguro', currency: 'USD', status: 'Active', last4: '1111' }] }))
    await Promise.resolve()
    expect(screen.queryByText('Seguro')).toBeNull()
    answers.two(ok())
    await screen.findByText('Cuenta de ahorro')
    await waitFor(() => expect(screen.queryByText('Seguro')).toBeNull())
  })
})
