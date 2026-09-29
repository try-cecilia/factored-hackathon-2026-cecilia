import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/context'
import type { DeskStatus, Result, Ticket } from '../../server/operator.functions'
import { renderWithI18n } from '../../test/render'
import { TicketScreen } from './TicketScreen'

const NOW = Date.now() / 1000
const ticket = (status: DeskStatus, version: number, history: Ticket['desk']['history'] = []): Ticket => ({
  ticket_id: 'a91f3c00', trace_id: null, created_at: NOW - 600, category: 'trace_review', priority: 'High', queue: 'payments_ops', customer_id: 'C-1',
  session_ref: 'sess-1', segment: 'Retail', country: 'México', language: 'es', request: 'Rastrear el pago.', prior_requests: [], reason: 'r', policy_rule: 'trace_review',
  verified_facts: [], evidence: [], actions_taken: [], open_questions: [], suggested_next_step: 's',
  pending_action: { tool: 'request_trace', transaction_id: 'tx1', product_id: 'p1' },
  desk: { ticket_id: 'a91f3c00', status, operator: status === 'open' ? null : 'ana.ruiz', trace_id: null, version, history },
})
const ok = (t: Ticket): Result<Ticket> => ({ ok: true, data: t })
const view = { canAct: true, operator: 'ana.ruiz' }

describe('TicketScreen when the case can no longer be read', () => {
  it('keeps the panel, and its 409 lock, on screen instead of replacing it with an error', async () => {
    const act = vi.fn(async () => ({ ok: false as const, status: 409, message: 'the ticket changed' }))
    const props = { ticketId: 'a91f3c00', view, act, reload: async () => true, onClose: () => {} }
    const { rerender } = renderWithI18n(<TicketScreen {...props} result={ok(ticket('claimed', 3))} />)
    await userEvent.setup().click(screen.getByRole('button', { name: /Aprobar rastreo/ }))
    const released = [{ action: 'release', status: 'handed_back', operator: 'diego.m', ts: NOW - 60, detail: {} }]
    rerender(<I18nProvider locale="es"><TicketScreen {...props} result={ok(ticket('open', 4, released))} /></I18nProvider>)
    await screen.findByText('No se aplicó: el caso cambió')

    // The next read fails with a 503: what the operator was looking at must stay, with the reason it is not fresh.
    rerender(<I18nProvider locale="es"><TicketScreen {...props} result={{ ok: false, status: 503 }} /></I18nProvider>)
    expect(screen.getByText('No se aplicó: el caso cambió')).toBeTruthy()
    expect(screen.getByText('No se pudo recargar el caso')).toBeTruthy()
    expect(screen.getByText(/servicio no está disponible/)).toBeTruthy()
    expect((screen.getByRole('button', { name: /Tomar caso/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('a case that was never read shows the error, and another case never inherits the last one', () => {
    const props = { view, act: vi.fn(), reload: async () => true, onClose: () => {} }
    const { rerender } = renderWithI18n(<TicketScreen {...props} ticketId="a91f3c00" result={ok(ticket('open', 0))} />)
    expect(screen.getByRole('button', { name: /Tomar caso/ })).toBeTruthy()
    rerender(<I18nProvider locale="es"><TicketScreen {...props} ticketId="other-case" result={{ ok: false, status: 404 }} /></I18nProvider>)
    expect(screen.queryByRole('button', { name: /Tomar caso/ })).toBeNull()
    expect(screen.getByRole('alert')).toBeTruthy()
  })
})
