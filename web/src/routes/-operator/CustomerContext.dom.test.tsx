import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CustomerContext } from '../../server/customer-context'
import type { Result } from '../../server/operator.functions'
import { I18nProvider } from '../../i18n/context'
import { dictionaries, renderWithI18n } from '../../test/render'
import { CasesFold, ContextNotice, MovementsFold, ProductsFold, TracesFold, useCustomerContext, type CaseLink } from './CustomerContext'
import { FoldGroup } from './Folds'

const NOW = Date.now() / 1000
const data = (over: Partial<CustomerContext> = {}): CustomerContext => ({
  warehouse: { available: true, as_of: '2026-06-01', source: 'account_warehouse', queried_at: '2026-06-01T12:34:56+00:00', freshness: 'current' },
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

/** The sections the panel draws from the customer, in the order it draws them. */
function Sections({ ticketId = 't1', load, caseLink }: { ticketId?: string; load: (id: string) => Promise<Result<CustomerContext>>; caseLink?: CaseLink }) {
  const { result, retry } = useCustomerContext(ticketId, load)
  const customer = result?.ok ? result.data : null
  return (
    <FoldGroup>
      <ContextNotice result={result} onRetry={retry} />
      {customer?.warehouse.available && (
        <>
          <ProductsFold data={customer} />
          <MovementsFold data={customer} />
        </>
      )}
      {customer && (
        <>
          <CasesFold data={customer} caseLink={caseLink} />
          <TracesFold data={customer} />
        </>
      )}
    </FoldGroup>
  )
}

const draw = async (result: Result<CustomerContext>, locale: 'es' | 'pt' = 'es', caseLink?: CaseLink) => {
  const utils = renderWithI18n(<Sections load={async () => result} caseLink={caseLink} />, locale)
  await screen.findByRole('region', { name: locale === 'es' ? 'Secciones' : 'Seções' })
  await waitFor(() => expect(document.querySelector('[aria-busy]')).toBeNull())
  return utils
}
const fold = (name: RegExp | string) => screen.getByRole('button', { name })
const unfold = async (name: RegExp | string) => userEvent.setup().click(fold(name))

describe('the customer sections of a case', () => {
  it('say what is in each one while it is closed', async () => {
    await draw(ok())
    expect(fold(/^Productos/).textContent).toContain('2 · 1 bloqueado')
    expect(fold(/^Movimientos/).textContent).toContain('1 pendiente')
    expect(fold(/^Otros casos/).textContent).toContain('1 · 1 abierto')
    expect(fold(/^Rastreos/).textContent).toContain('1')
    for (const name of [/^Productos/, /^Movimientos/, /^Otros casos/, /^Rastreos/]) expect(fold(name).getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('Cuenta de ahorro')).toBeNull()
  })

  it('shows the source, query time, data date, and original currency to the operator', async () => {
    await draw(ok())
    await unfold(/^Productos/)
    expect(document.body.textContent).toContain('Fuente: Almacén de cuentas y pagos')
    expect(document.body.textContent).toContain('Consultado: 2026-06-01T12:34:56+00:00')
    expect(document.body.textContent).toContain('Datos al 2026-06-01')
    expect((document.body.textContent?.match(/Moneda original: USD/g) ?? [])).toHaveLength(2)
  })

  it('explains stale account data and still shows its provenance', async () => {
    await draw(ok({ warehouse: { ...data().warehouse, available: false, as_of: '2024-01-16', freshness: 'stale' } }))
    expect(screen.getByText(/Los datos están vencidos al 2024-01-16/)).toBeTruthy()
    expect(document.body.textContent).toContain('Fuente: Almacén de cuentas y pagos')
    expect(document.body.textContent).toContain('Consultado: 2026-06-01T12:34:56+00:00')
  })

  it('shows the products by type with the last four digits only, and never a number that is longer', async () => {
    await draw(ok())
    await unfold(/^Productos/)
    expect(screen.getByText('Cuenta de ahorro')).toBeTruthy()
    expect(screen.getByText('Tarjeta de crédito')).toBeTruthy()
    expect(screen.getByText('•••• 0001')).toBeTruthy()
    expect(screen.getByText('Terminada en 0001').className).toContain('sr-only') // read once: the dots are hidden from a screen reader
    expect(screen.getByText('•••• 0001').getAttribute('aria-hidden')).toBe('true')
    expect(screen.getByText('Bloqueado')).toBeTruthy()
    for (const product of screen.getAllByRole('listitem')) expect(product.textContent).not.toMatch(/\d{5,}/)
  })

  it('says how many products are blocked and how many are inactive for another reason, in singular and plural', async () => {
    const product = (id: string, status: string) => ({ product_id: id, type: 'Seguro', currency: 'USD', status, last4: null })
    await draw(ok({ products: [product('a', 'Blocked'), product('b', 'Blocked'), product('c', 'Suspended'), product('d', 'Active')] }))
    expect(fold(/^Productos/).textContent).toContain('4 · 2 bloqueados · 1 inactivo')
  })

  it('puts the pending movement first and says it in words, then the three most recent, and the rest on request', async () => {
    const more = Array.from({ length: 6 }, (_, i) => ({ transaction_id: `TXN-${i}`, date: `2026-05-2${i}T09:00:00`, product_id: 'PRD-1', type: 'Purchase', amount: i + 1, currency: 'USD', merchant: `Comercio ${i}`, status: 'Approved', pending: false }))
    const [pending] = data().movements
    await draw(ok({ movements: [...more.slice(0, 2), pending, ...more.slice(2)] }))
    await unfold(/^Movimientos/)
    const rows = () => screen.getAllByRole('listitem')
    expect(rows()).toHaveLength(4) // the pending one and the three most recent
    expect(rows()[0].hasAttribute('data-pending')).toBe(true)
    expect(rows()[0].textContent).toContain('Transferencia')
    expect(rows()[0].textContent).toContain('Pendiente')
    expect(rows()[0].textContent).toContain('40.00 USD')
    expect(rows()[1].textContent).toContain('Compra · Comercio 0')
    expect(rows()[1].textContent).not.toContain('Aprobad') // approved is the plain state: not repeated on every row
    await userEvent.setup().click(screen.getByRole('button', { name: 'Ver los 7 movimientos' }))
    expect(rows()).toHaveLength(7)
    expect(screen.queryByRole('button', { name: /Ver los/ })).toBeNull()
  })

  it('has no "see all" when the movements fit, and marks a declined one', async () => {
    await draw(ok())
    await unfold(/^Movimientos/)
    expect(screen.queryByRole('button', { name: /Ver los/ })).toBeNull()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByText('Rechazado')).toBeTruthy()
    expect(screen.getByText('Datos al 2026-06-01')).toBeTruthy()
  })

  it('shows the count of movements when none is pending', async () => {
    await draw(ok({ movements: data().movements.slice(1) }))
    expect(fold(/^Movimientos/).textContent).toContain('2')
    expect(fold(/^Movimientos/).textContent).not.toContain('pendiente')
  })

  it.each([
    ['es', 1, '1 pendiente', 'y 1 pendiente más'],
    ['es', 7, '7 pendientes', 'y 7 pendientes más'],
    ['pt', 1, '1 pendente', 'e mais 1 pendente'],
    ['pt', 100, '100 pendentes', 'e mais 100 pendentes'],
  ] as const)('counts pending movements in the singular and the plural of the language, never as "(s)" (%s, %i)', async (locale, count, counted, left) => {
    const movements = Array.from({ length: count }, (_, i) => ({ transaction_id: `TXN-${i}`, date: '2026-05-30T10:00:00', product_id: 'PRD-1', type: 'Transfer', amount: 1, currency: 'USD', merchant: null, status: 'Pending', pending: true }))
    const { container } = await draw(ok({ movements, pending_omitted: count }), locale)
    expect(within(screen.getByRole('button', { name: /^Movimi?[ée]ntos|^Movimentações/ })).getByText(counted)).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: /^Movimientos|^Movimentações/ }))
    expect(screen.getByText(left)).toBeTruthy()
    expect(container.textContent).not.toContain('(s)')
  })

  it('says nothing about movements left out when it leaves none', async () => {
    await draw(ok())
    await unfold(/^Movimientos/)
    expect(screen.queryByText(/pendientes? más/)).toBeNull()
  })

  it('lists the other cases with a link to each and the rastreos of the customer', async () => {
    await draw(ok(), 'es', (id, label) => <a href={`/operador/cola/${id}`}>{label}</a>)
    await unfold(/^Otros casos/)
    await unfold(/^Rastreos/)
    const link = screen.getByRole('link', { name: 'a91f3c00' })
    expect(link.getAttribute('href')).toBe('/operador/cola/a91f3c00-1111')
    expect(screen.getByText(/Fraude/)).toBeTruthy()
    expect(screen.getByText('Tomado')).toBeTruthy()
    expect(screen.getByText('TR-ABCDEF0123456789')).toBeTruthy()
    expect(screen.getByText(/Movimiento TXN-9 · Abierto/)).toBeTruthy()
  })

  it('counts as open the cases that are not closed', async () => {
    const closed = { ticket_id: 'b', category: 'fraud', queue: 'q', priority: 'Low', created_at: NOW - 100, status: 'approved' }
    const waiting = { ticket_id: 'c', category: 'fraud', queue: 'q', priority: 'Low', created_at: NOW - 100, status: 'open' }
    await draw(ok({ cases: [...data().cases, closed, waiting] }))
    expect(fold(/^Otros casos/).textContent).toContain('3 · 2 abiertos')
  })

  it('a section with nothing in it is quiet, says "Ninguno" and does not open', async () => {
    await draw(ok({ products: [], movements: [], cases: [], traces: [] }))
    for (const name of ['Productos', 'Movimientos', 'Otros casos', 'Rastreos']) {
      expect(screen.queryByRole('button', { name: new RegExp(`^${name}`) })).toBeNull()
      expect(screen.getByText(name).closest('.op-fold')?.textContent).toContain('Ninguno')
    }
  })

  it('speaks Portuguese to a Portuguese operator, with the warehouse words translated', async () => {
    await draw(ok(), 'pt')
    expect(fold(/^Produtos/).textContent).toContain('2 · 1 bloqueado')
    await unfold(/^Produtos/)
    expect(screen.getByText('Conta poupança')).toBeTruthy()
    expect(screen.getByText('Final 0001').className).toContain('sr-only')
    await unfold(/^Movimentações/)
    expect(screen.getByText('Transferência')).toBeTruthy()
    expect(screen.getByText('Recusada')).toBeTruthy()
  })

  it('a value the console does not know is shown as it came', async () => {
    await draw(ok({ products: [{ product_id: 'P', type: 'Fideicomiso', currency: 'ARS', status: 'Dormant', last4: null }] }))
    expect(fold(/^Productos/).textContent).toContain('1 · 1 inactivo')
    await unfold(/^Productos/)
    expect(screen.getByText('Fideicomiso')).toBeTruthy()
    expect(screen.getByText('Dormant')).toBeTruthy()
    expect(screen.getByText('••••')).toBeTruthy()
  })

  it('a warehouse that is down says so, and the cases and rastreos are still there', async () => {
    await draw(ok({ warehouse: { ...data().warehouse, available: false, as_of: null, freshness: 'unavailable' }, products: [], movements: [] }))
    expect(screen.getByText('Los productos y movimientos del cliente no están disponibles ahora.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /^Productos|^Movimientos/ })).toBeNull()
    await unfold(/^Rastreos/)
    expect(screen.getByText('TR-ABCDEF0123456789')).toBeTruthy()
    await unfold(/^Otros casos/)
    expect(screen.getByText('Tomado')).toBeTruthy()
  })
})

describe('reading it', () => {
  it('shows that it is loading, then the sections; the case itself never waits for it', async () => {
    let finish!: (r: Result<CustomerContext>) => void
    const load = vi.fn(() => new Promise<Result<CustomerContext>>((done) => (finish = done)))
    renderWithI18n(<Sections load={load} />)
    expect(screen.getByText('Cargando el contexto del cliente')).toBeTruthy()
    expect(screen.getByText('Contexto del cliente').closest('[aria-busy]')?.getAttribute('aria-busy')).toBe('true')
    finish(ok())
    await screen.findByRole('button', { name: /^Productos/ })
    expect(document.querySelector('[aria-busy]')).toBeNull()
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('a failed read says the context is not available, that the rest of the case works, and can be tried again', async () => {
    const load = vi.fn<(id: string) => Promise<Result<CustomerContext>>>()
    load.mockResolvedValueOnce({ ok: false, status: 503 }).mockResolvedValueOnce(ok())
    renderWithI18n(<Sections load={load} />)
    await screen.findByText('El contexto del cliente no está disponible ahora. El resto del caso funciona igual.')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByRole('button', { name: /^Productos/ })
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('an expired session says so instead of offering to try again', async () => {
    renderWithI18n(<Sections load={async () => ({ ok: false, status: 401 })} />)
    await screen.findByText(/La sesión venció/)
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('an answer that arrives late for the previous case is not shown on the next one', async () => {
    const answers: Record<string, (r: Result<CustomerContext>) => void> = {}
    const load = (id: string) => new Promise<Result<CustomerContext>>((done) => (answers[id] = done))
    const view = renderWithI18n(<Sections ticketId="one" load={load} />)
    view.rerender(<I18nProvider locale="es" messages={dictionaries.es}><Sections ticketId="two" load={load} /></I18nProvider>)
    answers.one(ok({ products: [{ product_id: 'X', type: 'Seguro', currency: 'USD', status: 'Active', last4: '1111' }] }))
    await Promise.resolve()
    expect(screen.queryByRole('button', { name: /^Productos/ })).toBeNull()
    answers.two(ok())
    await screen.findByRole('button', { name: /^Productos/ })
    expect(fold(/^Productos/).textContent).toContain('2 · 1 bloqueado')
  })

  it('what the operator opened stays open when the context is read again', async () => {
    const down = ok({ warehouse: { ...data().warehouse, available: false, as_of: null, freshness: 'unavailable' }, products: [], movements: [] })
    const load = vi.fn<(id: string) => Promise<Result<CustomerContext>>>()
    load.mockResolvedValueOnce(down).mockResolvedValueOnce(ok())
    renderWithI18n(<Sections load={load} />)
    await screen.findByText('Los productos y movimientos del cliente no están disponibles ahora.')
    await unfold(/^Rastreos/)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByRole('button', { name: /^Productos/ })
    expect(fold(/^Rastreos/).getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('TR-ABCDEF0123456789')).toBeTruthy()
  })
})
