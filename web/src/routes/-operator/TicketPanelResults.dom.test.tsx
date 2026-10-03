import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DeskState, DeskStatus, Ticket } from '../../server/operator.functions'
import { renderWithI18n } from '../../test/render'
import { TicketPanel, type TicketPanelProps } from './TicketPanel'

// The demo's bank side resolves with a predefined result of the case's family, required, and an optional message (resolveOptions).
// The console's own resolution, without the prop, is pinned in TicketPanel.dom.test.tsx and stays as it was.

const NOW = Date.now() / 1000
const options = [
  { code: 'charge_confirmed', label: 'El cargo es una operación válida' },
  { code: 'will_contact', label: 'El banco contactará al cliente' },
]

function ticket(status: DeskStatus, desk: Partial<DeskState> & { result?: string | null } = {}): Ticket {
  return {
    ticket_id: 'b99d8390', trace_id: 'trace-1', created_at: NOW - 60, category: 'fraud', priority: 'Critical', queue: 'fraud_ops',
    customer_id: 'CLI-FIX0001', session_ref: 'sess-1', segment: 'Premium', country: 'México', language: 'es',
    request: 'No reconozco un cargo de mi tarjeta de crédito', prior_requests: [], reason: 'Fraud signal', policy_rule: 'lexicon',
    verified_facts: [], evidence: [], actions_taken: [], open_questions: [], suggested_next_step: 'Llamar al cliente.', pending_action: null,
    desk: { ticket_id: 'b99d8390', status, operator: status === 'open' ? null : 'demo', trace_id: null, version: status === 'open' ? 0 : 1, history: [], ...desk },
  }
}

function setup(t: Ticket, over: Partial<TicketPanelProps> = {}) {
  const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: true, data: t.desk }))
  const reload = vi.fn(async () => true)
  renderWithI18n(<TicketPanel ticket={t} view={{ canAct: true, operator: 'demo' }} act={act} reload={reload} resolveOptions={options} auditNote="Lo tomaste tú" {...over} />)
  return { act, reload }
}

const resolveButton = () => screen.getByRole('button', { name: /^Resolver/ }) as HTMLButtonElement

describe('resolving with a predefined result', () => {
  it('the results wait for the case to be taken, like the message', () => {
    setup(ticket('open'))
    const group = screen.getByRole('group', { name: 'Resultado para el cliente' })
    expect(group.matches(':disabled')).toBe(true)
    expect(screen.getByLabelText(/Mensaje para el cliente \(opcional\)/).matches(':disabled')).toBe(true)
    expect(screen.queryByRole('button', { name: /^Resolver/ })).toBeNull()
  })

  it('a result is required; the message is not: the result alone resolves', async () => {
    const { act } = setup(ticket('claimed'))
    expect(resolveButton().disabled).toBe(true)
    expect(screen.getByText('Lo tomaste tú')).toBeTruthy()
    const user = userEvent.setup()
    await user.click(screen.getByRole('radio', { name: 'El banco contactará al cliente' }))
    expect(resolveButton().disabled).toBe(false)
    await user.click(resolveButton())
    expect(act).toHaveBeenCalledWith('resolve', { expectedVersion: 1, reason: undefined, message: undefined, resultCode: 'will_contact' })
  })

  it('a message goes with the result, trimmed; the result is never replaced by it', async () => {
    const { act } = setup(ticket('claimed', { version: 4 }))
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Mensaje para el cliente \(opcional\)/), '  Ya hablamos con el comercio.  ')
    expect(resolveButton().disabled).toBe(true)
    await user.click(screen.getByRole('radio', { name: 'El cargo es una operación válida' }))
    await user.click(resolveButton())
    expect(act).toHaveBeenCalledWith('resolve', { expectedVersion: 4, reason: undefined, message: 'Ya hablamos con el comercio.', resultCode: 'charge_confirmed' })
    expect(screen.getByText('Le llega en el chat después del resultado, marcado como escrito por una persona.')).toBeTruthy()
  })

  it('a 409 locks the decision like in the console, and reads the case again', async () => {
    const t = ticket('claimed')
    const { act, reload } = setup(t)
    act.mockResolvedValueOnce({ ok: false, status: 409, message: 'another person took this case' })
    const user = userEvent.setup()
    await user.click(screen.getByRole('radio', { name: 'El banco contactará al cliente' }))
    await user.click(resolveButton())
    await waitFor(() => expect(reload).toHaveBeenCalledWith(1))
    expect(screen.getByText('another person took this case')).toBeTruthy()
    expect(screen.getByRole('group', { name: 'Resultado para el cliente' }).matches(':disabled')).toBe(true)
  })

  it('a resolved case shows the result by its name, and the message the customer got', () => {
    setup(ticket('resolved', { result: 'charge_confirmed', message: 'Ya hablamos con el comercio.', history: [{ action: 'resolve', status: 'resolved', operator: 'demo', ts: NOW, detail: { message: 'Ya hablamos con el comercio.', result: 'charge_confirmed' } }] }))
    expect(screen.getByText('Resultado: El cargo es una operación válida')).toBeTruthy()
    expect(screen.getByText(/Ya hablamos con el comercio\./, { selector: '.op-outcome p' })).toBeTruthy()
    expect(screen.queryByRole('group', { name: 'Resultado para el cliente' })).toBeNull()
  })

  it('a case that carries an action is still approved or rejected: no results to pick', () => {
    const t = { ...ticket('claimed'), pending_action: { tool: 'request_trace', transaction_id: 'tx_1', product_id: 'P-1' } }
    setup(t, { resolveOptions: [] })
    expect(screen.queryByRole('group', { name: 'Resultado para el cliente' })).toBeNull()
    expect(screen.getByRole('button', { name: /Aprobar rastreo/ })).toBeTruthy()
  })
})
