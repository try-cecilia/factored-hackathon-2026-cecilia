import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DeskState, DeskStatus, Ticket } from '../../server/operator.functions'
import { I18nProvider } from '../../i18n/context'
import { renderWithI18n } from '../../test/render'
import { TicketPanel, type TicketPanelProps } from './TicketPanel'

const NOW = Date.now() / 1000

function ticket(status: DeskStatus = 'open', over: Partial<Ticket> = {}, desk: Partial<DeskState> = {}): Ticket {
  return {
    ticket_id: 'a91f3c00', trace_id: 'trace-1234abcd', created_at: NOW - 26 * 60, category: 'trace_review', priority: 'High', queue: 'payments_ops',
    customer_id: 'C-1', session_ref: 'sess-7e2c9ab1', segment: 'Retail', country: 'MX', language: 'es',
    request: 'Hice un pago que sigue pendiente y quiero que lo rastreen.', prior_requests: [], reason: 'Trace on a pending movement needs review',
    policy_rule: 'trace_review', verified_facts: [{ tool: 'get_payment_status', outcome: 'ok' }], evidence: [], actions_taken: [],
    open_questions: ['¿Autorizó el cliente el cargo?'], suggested_next_step: 'Llamar al cliente.',
    pending_action: { tool: 'request_trace', transaction_id: 'tx_88210', product_id: 'PRD-4821', review_reason: 'older_than_review_threshold', age_days: 47, movement: { transaction_type: 'payment', amount: 12400, currency: 'MXN' } },
    desk: { ticket_id: 'a91f3c00', status, operator: status === 'open' ? null : 'ana.ruiz', trace_id: null, version: status === 'open' ? 0 : 1, history: [], ...desk },
    ...over,
  }
}

function setup(t: Ticket, view: TicketPanelProps['view'] = { canAct: true, operator: 'ana.ruiz' }, over: Partial<TicketPanelProps> = {}) {
  const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: true, data: t.desk }))
  const reload = vi.fn(async () => true)
  const utils = renderWithI18n(<TicketPanel ticket={t} view={view} act={act} reload={reload} keyForm={<form aria-label="Clave de operador" />} {...over} />)
  return { act, reload, ...utils }
}

const button = (name: RegExp) => screen.queryByRole('button', { name })
const disabled = (el: HTMLElement | null) => (el as HTMLButtonElement | HTMLTextAreaElement).disabled

describe('unassigned', () => {
  it('offers to claim, and nothing else to decide', async () => {
    const { act } = setup(ticket('open'))
    expect(disabled(button(/Tomar caso/))).toBe(false)
    expect(button(/Aprobar rastreo/)).toBeNull()
    expect(button(/^Rechazar/)).toBeNull()
    expect(disabled(screen.getByLabelText(/Motivo del rechazo/))).toBe(true)
    await userEvent.setup().click(button(/Tomar caso/)!)
    expect(act).toHaveBeenCalledWith('claim', { expectedVersion: 0, reason: undefined })
  })

  it('a read-only session cannot claim and is asked for an operator key', () => {
    setup(ticket('open'), { canAct: false, operator: null })
    expect(button(/Tomar caso/)).toBeNull()
    expect(screen.getByRole('form', { name: 'Clave de operador' })).toBeTruthy()
  })
})

describe('claimed', () => {
  it('the holder can approve, reject and release, always with the version on screen', async () => {
    const t = ticket('claimed', {}, { version: 2 })
    const { act } = setup(t)
    const user = userEvent.setup()
    expect(disabled(screen.getByLabelText(/Motivo del rechazo/))).toBe(false)
    await user.click(button(/Aprobar rastreo/)!)
    expect(act).toHaveBeenLastCalledWith('approve', { expectedVersion: 2, reason: undefined })
    await user.type(screen.getByLabelText(/Motivo del rechazo/), '  duplicado ')
    await user.click(button(/^Rechazar/)!)
    expect(act).toHaveBeenLastCalledWith('reject', { expectedVersion: 2, reason: 'duplicado' })
    await user.click(button(/Devolver a la asistente/)!)
    expect(act).toHaveBeenLastCalledWith('release', { expectedVersion: 2, reason: undefined })
  })

  it('without an action to approve there is no approve button', () => {
    setup(ticket('claimed', { pending_action: null }, { version: 1 }))
    expect(button(/Aprobar rastreo/)).toBeNull()
    expect(button(/^Rechazar/)).toBeTruthy()
  })

  it('someone else holds it: nobody else can decide it', () => {
    setup(ticket('claimed', {}, { operator: 'diego.m', version: 1 }))
    expect(button(/Aprobar rastreo/)).toBeNull()
    expect(button(/^Rechazar/)).toBeNull()
    expect(button(/Devolver a la asistente/)).toBeNull()
    expect(screen.getAllByText(/Tomado por diego\.m/).length).toBeGreaterThan(0)
  })
})

describe('version conflict (409)', () => {
  it('shows the conflict panel, locks the decision and reloads on demand', async () => {
    const seen = ticket('claimed', {}, { version: 3 })
    const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: false, status: 409, message: 'the ticket changed (you saw version 3, now 4)' }))
    const reload = vi.fn(async () => true)
    const { rerender } = renderWithI18n(<TicketPanel ticket={seen} view={{ canAct: true, operator: 'ana.ruiz' }} act={act} reload={reload} />)
    const user = userEvent.setup()
    await user.click(button(/Aprobar rastreo/)!)
    expect(reload).toHaveBeenCalledTimes(1)

    // The server now holds v4: diego.m took it back to the assistant.
    const now = ticket('open', {}, { version: 4, history: [{ action: 'release', status: 'handed_back', operator: 'diego.m', ts: NOW - 60, detail: {} }] })
    rerender(<I18nProvider locale="es"><TicketPanel ticket={now} view={{ canAct: true, operator: 'ana.ruiz' }} act={act} reload={reload} /></I18nProvider>)
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('No se aplicó: el caso cambió')).toBeTruthy()
    expect(alert.textContent).toMatch(/v3.*v4.*diego\.m lo devolvió a la asistente/)
    expect(screen.getByLabelText(/Versión 3, ahora 4/).textContent).toBe('v3 → v4')
    expect(disabled(button(/Tomar caso/))).toBe(true)

    await user.click(button(/Recargar caso/)!)
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(reload).toHaveBeenCalledTimes(2)
    expect(disabled(button(/Tomar caso/))).toBe(false)
  })

  it('any other failure is explained without locking the screen', async () => {
    const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: false, status: 503 }))
    setup(ticket('open'), undefined, { act })
    await userEvent.setup().click(button(/Tomar caso/)!)
    expect((await screen.findByRole('alert')).textContent).toMatch(/servicio no está disponible/)
    expect(disabled(button(/Tomar caso/))).toBe(false)
  })
})

describe('version conflict when the reload fails', () => {
  const view = { canAct: true, operator: 'ana.ruiz' }
  const release = [{ action: 'release', status: 'handed_back', operator: 'diego.m', ts: NOW - 60, detail: {} }]

  async function conflicted(reload: TicketPanelProps['reload']) {
    const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: false, status: 409, message: 'the ticket changed' }))
    const utils = renderWithI18n(<TicketPanel ticket={ticket('claimed', {}, { version: 3 })} view={view} act={act} reload={reload} />)
    const user = userEvent.setup()
    await user.click(button(/Aprobar rastreo/)!)
    utils.rerender(<I18nProvider locale="es"><TicketPanel ticket={ticket('open', {}, { version: 4, history: release })} view={view} act={act} reload={reload} /></I18nProvider>)
    await screen.findByText('No se aplicó: el caso cambió')
    return { user, act }
  }

  it('keeps the lock, and says so, when the explicit reload did not work', async () => {
    const reload = vi.fn<TicketPanelProps['reload']>().mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const { user } = await conflicted(reload)
    await user.click(button(/Recargar caso/)!)
    await screen.findByText('No se pudo recargar el caso')
    expect(screen.getByText('No se aplicó: el caso cambió')).toBeTruthy()
    expect(disabled(button(/Tomar caso/))).toBe(true)
    // A later reload that works is what lifts it.
    reload.mockResolvedValueOnce(true)
    await user.click(button(/Recargar caso/)!)
    await waitFor(() => expect(screen.queryByText('No se aplicó: el caso cambió')).toBeNull())
    expect(screen.queryByText('No se pudo recargar el caso')).toBeNull()
    expect(disabled(button(/Tomar caso/))).toBe(false)
  })

  it('a reload that throws is a failed reload too', async () => {
    const reload = vi.fn<TicketPanelProps['reload']>().mockResolvedValueOnce(true).mockRejectedValueOnce(new Error('offline'))
    const { user } = await conflicted(reload)
    await user.click(button(/Recargar caso/)!)
    await screen.findByText('No se pudo recargar el caso')
    expect(screen.getByText('No se aplicó: el caso cambió')).toBeTruthy()
  })
})

describe('decided', () => {
  it('is read-only and says how it ended', () => {
    const closed = ticket('approved', {}, { version: 3, trace_id: 'trace_6f3a91c2', history: [{ action: 'approve', status: 'approved', operator: 'lucia.g', ts: NOW - 300, detail: {} }] })
    setup(closed)
    expect(screen.getByText('Rastreo abierto')).toBeTruthy()
    expect(screen.getByText(/trace_6f3a91c2/)).toBeTruthy()
    expect(screen.getByText('Cerrado · sin más acciones')).toBeTruthy()
    expect(button(/Tomar caso|Aprobar rastreo|^Rechazar|Devolver a la asistente/)).toBeNull()
    expect(screen.queryByLabelText(/Motivo del rechazo/)).toBeNull()
    expect(button(/Copiar resumen/)).toBeTruthy()
    expect(screen.getAllByText(/Aprobado por lucia\.g/).length).toBeGreaterThan(0)
  })

  it('a stale approval says nothing was opened', () => {
    setup(ticket('stale', {}, { version: 2, history: [{ action: 'approve', status: 'stale', operator: 'ana.ruiz', ts: NOW - 30, detail: {} }] }))
    expect(screen.getByText('El movimiento ya no estaba pendiente')).toBeTruthy()
  })
})

describe('evidence', () => {
  it('marks the transactions with a score of 70 or more, and counts them', () => {
    const rows = [
      { id: 'tx1', score: 91, merchant: 'Amazon MX' },
      { id: 'tx2', score: 70, merchant: 'DigitalOcean' },
      { id: 'tx3', score: 69, merchant: 'Oxxo' },
      { id: 'tx4', score: 8, merchant: 'Uber' },
    ]
    setup(ticket('claimed', {
      evidence: rows.map((r) => ({
        type: 'transaction', id: r.id, flagged: r.score >= 70,
        detail: { transaction_date: '2026-09-28T14:02:00', amount: 199, currency: 'USD', merchant_name: r.merchant, transaction_country: 'US', fraud_score: r.score },
      })),
    }, { version: 1 }))
    expect(screen.getByText('2 marcadas · score 70+')).toBeTruthy()
    const table = screen.getByRole('table', { name: 'Movimientos recientes del cliente' })
    const flagged = within(table).getAllByRole('row').filter((row) => row.hasAttribute('data-flagged'))
    expect(flagged.map((row) => within(row).getAllByRole('cell')[2].textContent)).toEqual(['Amazon MX · US', 'DigitalOcean · US'])
    expect(within(flagged[0]).getByText('Marcado, score 91')).toBeTruthy()
  })
})

describe('portuguese', () => {
  it('draws the same panel in the other language', () => {
    renderWithI18n(<TicketPanel ticket={ticket('open')} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} />, 'pt')
    expect(disabled(button(/Assumir caso/))).toBe(false)
    expect(screen.getByText('Solicitação')).toBeTruthy()
  })
})
