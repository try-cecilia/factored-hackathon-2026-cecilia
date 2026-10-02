import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CustomerContext } from '../../server/customer-context'
import type { DeskState, DeskStatus, Ticket } from '../../server/operator.functions'
import { I18nProvider } from '../../i18n/context'
import { renderWithI18n, dictionaries } from '../../test/render'
import { TicketPanel, type TicketPanelProps } from './TicketPanel'
import { TicketScreen } from './TicketScreen'

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
/** The folding sections of the drawer start closed: the test opens the one it reads. */
const unfold = async (name: RegExp | string) => userEvent.setup().click(screen.getByRole('button', { name }))
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

  it('without an action to approve, the message for the customer waits for someone to take the case', () => {
    setup(ticket('open', { pending_action: null }))
    const box = screen.getByLabelText(/Mensaje para el cliente/) as HTMLTextAreaElement
    expect(box.disabled).toBe(true)
    expect(box.placeholder).toBe('Tomar el caso para escribir el mensaje')
    expect(button(/^Resolver/)).toBeNull()
    expect(screen.queryByLabelText(/Motivo del rechazo/)).toBeNull()
  })
})

describe('claimed', () => {
  it('the holder can approve, reject and release, always with the version on screen', async () => {
    const t = ticket('claimed', {}, { version: 2 })
    const { act } = setup(t)
    const user = userEvent.setup()
    expect(disabled(screen.getByLabelText(/Motivo del rechazo/))).toBe(false)
    // Resolving is for cases without an action: this one closes by approving or rejecting it.
    expect(button(/^Resolver/)).toBeNull()
    expect(screen.queryByLabelText(/Mensaje para el cliente/)).toBeNull()
    await user.click(button(/Aprobar rastreo/)!)
    expect(act).toHaveBeenLastCalledWith('approve', { expectedVersion: 2, reason: undefined })
    // The panel clears the reason once the action has answered and holds its buttons until it has read the case again: wait for the next one.
    await waitFor(() => expect(disabled(button(/^Rechazar/))).toBe(false))
    await user.type(screen.getByLabelText(/Motivo del rechazo/), '  duplicado ')
    await user.click(button(/^Rechazar/)!)
    expect(act).toHaveBeenLastCalledWith('reject', { expectedVersion: 2, reason: 'duplicado' })
    await waitFor(() => expect(disabled(button(/Devolver a la asistente/))).toBe(false))
    await user.click(button(/Devolver a la asistente/)!)
    expect(act).toHaveBeenLastCalledWith('release', { expectedVersion: 2, reason: undefined })
  })

  it('without an action to approve, the holder resolves it with a message for the customer or hands it back; there is nothing to reject', async () => {
    const { act } = setup(ticket('claimed', { pending_action: null }, { version: 1 }))
    const user = userEvent.setup()
    expect(button(/Aprobar rastreo/)).toBeNull()
    expect(button(/^Rechazar/)).toBeNull()
    expect(screen.queryByLabelText(/Motivo del rechazo/)).toBeNull()
    const box = screen.getByLabelText(/Mensaje para el cliente/) as HTMLTextAreaElement
    expect(box.maxLength).toBe(500)
    expect(disabled(button(/^Resolver/))).toBe(true)
    await user.type(box, '  ')
    expect(disabled(button(/^Resolver/))).toBe(true) // blank is not a message
    await user.type(box, 'Listo. ')
    expect(screen.getByText('9/500')).toBeTruthy()
    await user.click(button(/^Resolver/)!)
    expect(act).toHaveBeenLastCalledWith('resolve', { expectedVersion: 1, message: 'Listo.' })
    expect(await screen.findByText('Caso resuelto.')).toBeTruthy()
    expect(box.value).toBe('')
    // The notice comes before the case is read again, which is when the buttons are free.
    await waitFor(() => expect(disabled(button(/Devolver a la asistente/))).toBe(false))
    await user.click(button(/Devolver a la asistente/)!)
    expect(act).toHaveBeenLastCalledWith('release', { expectedVersion: 1 })
  })

  it('someone else holds it: nobody else can decide it', () => {
    setup(ticket('claimed', {}, { operator: 'diego.m', version: 1 }))
    expect(button(/Aprobar rastreo/)).toBeNull()
    expect(button(/^Rechazar/)).toBeNull()
    expect(button(/Devolver a la asistente/)).toBeNull()
    expect(screen.getAllByText(/Tomado por diego\.m/).length).toBeGreaterThan(0)
  })

  it('someone else holds a case without an action: nobody else can resolve it', () => {
    setup(ticket('claimed', { pending_action: null }, { operator: 'diego.m', version: 1 }))
    expect(button(/^Resolver/)).toBeNull()
    const box = screen.getByLabelText(/Mensaje para el cliente/) as HTMLTextAreaElement
    expect(box.disabled).toBe(true)
    expect(box.placeholder).toBe('Solo diego.m puede resolver este caso')
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
    // The panel reads the case again once the action has answered, after the click has returned.
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))

    // The server now holds v4: diego.m took it back to the assistant.
    const now = ticket('open', {}, { version: 4, history: [{ action: 'release', status: 'handed_back', operator: 'diego.m', ts: NOW - 60, detail: {} }] })
    rerender(<I18nProvider locale="es" messages={dictionaries.es}><TicketPanel ticket={now} view={{ canAct: true, operator: 'ana.ruiz' }} act={act} reload={reload} /></I18nProvider>)
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

  it('names a resolution as what changed the case', async () => {
    const view = { canAct: true, operator: 'ana.ruiz' }
    const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: false, status: 409, message: 'ticket is already resolved' }))
    const reload = vi.fn(async () => true)
    const { rerender } = renderWithI18n(<TicketPanel ticket={ticket('open', { pending_action: null })} view={view} act={act} reload={reload} />)
    await userEvent.setup().click(button(/Tomar caso/)!)
    const history: DeskState['history'] = [
      { action: 'claim', status: 'claimed', operator: 'diego.m', ts: NOW - 300, detail: {} },
      { action: 'resolve', status: 'resolved', operator: 'diego.m', ts: NOW - 60, detail: { message: 'Listo.' } },
    ]
    rerender(<I18nProvider locale="es" messages={dictionaries.es}><TicketPanel ticket={ticket('resolved', { pending_action: null }, { operator: 'diego.m', version: 2, message: 'Listo.', history })} view={view} act={act} reload={reload} /></I18nProvider>)
    expect((await screen.findByRole('alert')).textContent).toMatch(/v0.*v2.*diego\.m lo resolvió/)
  })

  it('on a case without an action, what stays locked is resolving, and the message is kept', async () => {
    const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: false, status: 409, message: 'the ticket changed' }))
    setup(ticket('claimed', { pending_action: null }, { version: 2 }), undefined, { act })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Mensaje para el cliente/), 'Listo.')
    await user.click(button(/^Resolver/)!)
    await screen.findByText('No se aplicó: el caso cambió')
    expect(disabled(button(/^Resolver/))).toBe(true)
    expect(button(/Aprobar rastreo|^Rechazar/)).toBeNull()
    const box = screen.getByLabelText(/Mensaje para el cliente/) as HTMLTextAreaElement
    expect(box.disabled).toBe(true)
    expect(box.value).toBe('Listo.')
  })

  it('any other failure is explained without locking the screen', async () => {
    const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: false, status: 503 }))
    setup(ticket('open'), undefined, { act })
    await userEvent.setup().click(button(/Tomar caso/)!)
    expect((await screen.findByRole('alert')).textContent).toMatch(/servicio no está disponible/)
    // The notice comes before the case is read again, which is when the button is free.
    await waitFor(() => expect(disabled(button(/Tomar caso/))).toBe(false))
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
    utils.rerender(<I18nProvider locale="es" messages={dictionaries.es}><TicketPanel ticket={ticket('open', {}, { version: 4, history: release })} view={view} act={act} reload={reload} /></I18nProvider>)
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
    expect(screen.getByText('Rastreo abierto').closest('.op-summary')).toBeTruthy()
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

describe('resolved', () => {
  const said = 'Revisamos el cargo: era una suscripción y ya no se repite.'
  const history: DeskState['history'] = [
    { action: 'claim', status: 'claimed', operator: 'lucia.g', ts: NOW - 600, detail: {} },
    { action: 'resolve', status: 'resolved', operator: 'lucia.g', ts: NOW - 120, detail: { message: said } },
  ]
  const outcome = () => screen.getByText('Caso resuelto').closest('[role="status"]') as HTMLElement

  it('says how it ended and quotes what the customer was told, in the summary and in the history', async () => {
    setup(ticket('resolved', { pending_action: null }, { operator: 'lucia.g', version: 2, message: said, history }))
    expect(outcome().textContent).toContain(`Mensaje de lucia.g: “${said}”`)
    expect(outcome().className).toContain('op-outcome--success')
    expect(outcome().closest('.op-summary')).toBeTruthy()
    expect(document.querySelector('.op-banner')).toBeNull() // the result is in the card, not in a banner
    expect(screen.getAllByText(/Resuelto por lucia\.g/).length).toBeGreaterThan(0)
    await unfold(/^Historial/)
    const item = screen.getAllByRole('listitem').find((li) => li.textContent?.startsWith('Resuelto por lucia.g'))
    expect(item?.textContent).toContain(`“${said}”`)
    expect(screen.getByText('Cerrado · sin más acciones')).toBeTruthy()
    expect(button(/Resolver|^Rechazar|Devolver a la asistente/)).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('an API that does not send the message still has it in the history', () => {
    setup(ticket('resolved', { pending_action: null }, { operator: 'lucia.g', version: 2, history }))
    expect(outcome().textContent).toContain(`“${said}”`)
  })
})

describe('evidence', () => {
  it('marks the transactions with a score of 70 or more, and counts them', async () => {
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
    expect(screen.getByRole('button', { name: /^Evidencia/ }).textContent).toContain('4 · 2 marcados')
    await unfold(/^Evidencia/)
    expect(screen.getByText('2 marcados · score 70+')).toBeTruthy()
    const list = screen.getByRole('list', { name: 'Movimientos recientes del cliente' })
    const flagged = within(list).getAllByRole('listitem').filter((row) => row.hasAttribute('data-flagged'))
    expect(flagged.map((row) => row.querySelector('.op-evrows__who')?.textContent)).toEqual(['Amazon MX · US', 'DigitalOcean · US'])
    expect(within(flagged[0]).getByText('Marcado, score 91')).toBeTruthy()
  })

  it('shows the deviation from the own history of the customer as a number and a word, never as a flag, and says what it is not', async () => {
    const detail = { transaction_date: '2026-09-28T14:02:00', amount: 199, currency: 'USD', merchant_name: 'Uber', transaction_country: 'US', fraud_score: 8 }
    setup(ticket('claimed', {
      evidence: [
        { type: 'transaction', id: 'tx1', flagged: false, detail: { ...detail, behavior: { composite: 62.4, band: 'elevated', components: {}, prior_count: 40 } } },
        { type: 'transaction', id: 'tx2', flagged: false, detail: { ...detail, behavior: { composite: null, band: null, components: {}, prior_count: 2 } } },
        { type: 'transaction', id: 'tx3', flagged: false, detail },
      ],
    }, { version: 1 }))
    expect(screen.getByRole('button', { name: /^Evidencia/ }).textContent).toContain('3')
    expect(screen.getByRole('button', { name: /^Evidencia/ }).textContent).not.toContain('marcados')
    await unfold(/^Evidencia/)
    const rows = within(screen.getByRole('list', { name: 'Movimientos recientes del cliente' })).getAllByRole('listitem')
    const deviation = (row: HTMLElement) => row.querySelector('.op-evrows__deviation')!.textContent
    expect(deviation(rows[0])).toBe('Desviación 62 · elevada')
    expect(deviation(rows[1])).toBe('Desviación —')
    expect(deviation(rows[2])).toBe('Desviación —')
    expect(rows.some((row) => row.hasAttribute('data-flagged'))).toBe(false)
    expect(screen.getByText(/no es una probabilidad de fraude ni una determinación de fraude/)).toBeTruthy()
  })
})

describe('the deviation of a movement', () => {
  const detail = { transaction_date: '2026-09-28T14:02:00', amount: 199, currency: 'USD', merchant_name: 'Uber', transaction_country: 'US', fraud_score: 8 }
  const withBehavior = (band: string) => ticket('claimed', {
    evidence: [
      { type: 'transaction', id: 'tx1', flagged: false, detail: { ...detail, behavior: { composite: 62.4, band, components: {}, prior_count: 40 } } },
      { type: 'transaction', id: 'tx2', flagged: false, detail },
    ],
  }, { version: 1 })

  it.each([
    ['es', 'elevated', 'Desviación 62 · elevada', /^Cuánto se aparta este movimiento del historial del propio cliente.*no es un modelo de fraude ni decide nada\.$/, 'Historial insuficiente para describirlo'],
    ['pt', 'moderate', 'Desvio 62 · moderado', /^Quanto esta movimentação se afasta do histórico do próprio cliente.*não é um modelo de fraude nem decide nada\.$/, 'Histórico insuficiente para descrever'],
  ] as const)('reads whole, and explains in %s what it is: how far the movement is from the own history, not a fraud model', async (locale, band, text, hint, none) => {
    renderWithI18n(<TicketPanel ticket={withBehavior(band)} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} />, locale)
    await userEvent.setup().click(screen.getByRole('button', { name: /^Evid/ }))
    const [shown, missing] = Array.from(document.querySelectorAll<HTMLElement>('.op-evrows__deviation'))
    expect(shown.textContent).toBe(text)
    expect(shown.title).toMatch(hint)
    expect(missing.title).toBe(none)
    // The same sentence is there for a screen reader, not only for a pointer: the visible note under the list.
    const note = document.getElementById(shown.getAttribute('aria-describedby')!)
    expect(note?.textContent).toMatch(/probabilidade de fraude|probabilidad de fraude/)
    expect(document.querySelector('table')).toBeNull() // no columns to cut: nothing is truncated or scrolled sideways
  })

  it('marks in "Movimientos" the ones that "Evidencia" already shows, and only those', async () => {
    const context: CustomerContext = {
      warehouse: { available: true, as_of: null }, products: [], pending_omitted: 0, cases: [], traces: [],
      movements: ['tx1', 'tx9'].map((id) => ({ transaction_id: id, date: '2026-09-28T14:02:00', product_id: 'P', type: 'Purchase', amount: 199, currency: 'USD', merchant: id, status: 'Approved', pending: false })),
    }
    setup(withBehavior('elevated'), undefined, { loadContext: async () => ({ ok: true, data: context }) })
    await userEvent.setup().click(await screen.findByRole('button', { name: /^Movimientos/ }))
    const rows = screen.getAllByRole('listitem').filter((li) => li.closest('.op-moves'))
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('En evidencia').title).toMatch(/también está en la sección Evidencia/)
    expect(within(rows[1]).queryByText('En evidencia')).toBeNull()
  })
})

describe('portuguese', () => {
  it('draws the same panel in the other language', () => {
    renderWithI18n(<TicketPanel ticket={ticket('open')} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} />, 'pt')
    expect(disabled(button(/Assumir caso/))).toBe(false)
    expect(screen.getByText('Solicitação')).toBeTruthy()
  })
})

// What the operator reads of the assistant's own decision: written from the codes of the case, in the operator's language, and the
// English text of the API wherever the case has no code (or one this console does not know).
describe('the texts of the case', () => {
  const english = {
    reason: 'The customer confirmed a trace, but the movement needs a person\'s approval (older_than_review_threshold).',
    policy_rule: 'action:trace_review',
    open_questions: ['Approve or reject the trace: older_than_review_threshold.', 'Could not gather recent activity automatically: IO Error: Cannot open file "C:/srv/data/warehouse/bank.duckdb"'],
    suggested_next_step: 'Review the movement (see pending_action.review_reason) and approve or reject the trace the customer asked for.',
    verified_facts: [{ tool: 'get_payment_status', result: { status: 'pending' } }],
    evidence: [{ type: 'denied_request', id: 'P-9', detail: { tool: 'get_account_summary' } }],
  }
  const codes: Pick<Ticket, 'reason_code' | 'open_question_codes' | 'next_step_code'> = {
    reason_code: { code: 'trace_review', params: { review_reason: 'older_than_review_threshold' } },
    open_question_codes: [{ code: 'decide_trace', params: { review_reason: 'older_than_review_threshold' } }, { code: 'evidence_failed', params: { error_type: 'OperationalError' } }],
    next_step_code: 'trace_review',
  }
  const view = { canAct: true, operator: 'ana.ruiz' }
  const panel = (t: Ticket, locale: 'es' | 'pt') =>
    renderWithI18n(<TicketPanel ticket={t} view={view} act={vi.fn()} reload={vi.fn(async () => true)} />, locale)
  const block = (heading: string) => screen.getByRole('button', { name: new RegExp(`^${heading}`) }).closest('.op-fold') as HTMLElement
  const nextStep = (heading: string) => screen.getByRole('heading', { name: heading }).closest('section') as HTMLElement

  it('in Spanish, from the codes', async () => {
    panel(ticket('open', { ...english, ...codes }), 'es')
    await unfold(/^Preguntas abiertas/)
    expect(screen.getByText(/^El cliente confirmó un rastreo, pero el movimiento necesita la aprobación de una persona \(Pendiente desde hace más tiempo/)).toBeTruthy()
    expect(screen.getByText(/regla Rastreo: lo decide una persona$/)).toBeTruthy()
    const questions = within(block('Preguntas abiertas')).getAllByRole('listitem').map((li) => li.textContent)
    expect(questions).toEqual(['Aprobar o rechazar el rastreo: Pendiente desde hace más tiempo del que admite un rastreo simple.', 'No se pudo reunir la actividad reciente automáticamente (OperationalError).'])
    expect(within(nextStep('Próximo paso sugerido')).getByText(/^Revisar el movimiento \(ver el motivo de revisión\)/)).toBeTruthy()
    expect(screen.queryByText(/Approve or reject|Review the movement|Could not gather/)).toBeNull()
  })

  it('in Portuguese, from the codes', async () => {
    panel(ticket('open', { ...english, ...codes }), 'pt')
    await unfold(/^Perguntas em aberto/)
    expect(screen.getByText(/^O cliente confirmou um rastreio, mas a movimentação precisa da aprovação de uma pessoa/)).toBeTruthy()
    const questions = within(block('Perguntas em aberto')).getAllByRole('listitem').map((li) => li.textContent)
    expect(questions).toEqual(['Aprovar ou rejeitar o rastreio: Pendente há mais tempo do que um rastreio simples admite.', 'Não foi possível reunir a atividade recente automaticamente (OperationalError).'])
    expect(within(nextStep('Próximo passo sugerido')).getByText(/^Revisar a movimentação/)).toBeTruthy()
  })

  // What a lookup raised is English and can carry ids and paths: the code carries the field or the type of error, so the operator
  // reads one sentence in their language, and the message stays in the English fallback (which the panel does not show over a code).
  const rawMessage = 'unexpected failure in get_account_summary: OperationalError: IO Error: Cannot open file "C:/srv/data/warehouse/bank.duckdb"'
  const failed = {
    reason: `Tool failure: ${rawMessage}`,
    open_questions: ['A lookup failed; answer requires a manual check.'],
    suggested_next_step: 'Answer manually from the core system and report the lookup that failed.',
    reason_code: { code: 'tool_failure', params: { error_type: 'ToolError' } },
    open_question_codes: [{ code: 'manual_check', params: {} }],
    next_step_code: 'tool_failure',
  }
  const missing = {
    reason: 'Data needed for a verified answer is unavailable: balance missing for product PRD-AB12CD34EF56',
    open_questions: ["Look up 'current_balance' in the core system."],
    suggested_next_step: 'Look up the missing data in the core system and answer the customer.',
    reason_code: { code: 'data_unavailable', params: { field: 'current_balance' } },
    open_question_codes: [{ code: 'lookup_field', params: { field: 'current_balance' } }],
    next_step_code: 'data_unavailable',
  }
  it.each([
    ['es', failed, 'Falló una consulta (ToolError): hace falta una verificación manual.'],
    ['pt', failed, 'Falhou uma consulta (ToolError): é preciso uma verificação manual.'],
    ['es', missing, 'Falta un dato necesario para responder con verificación: current_balance.'],
    ['pt', missing, 'Falta um dado necessário para responder com verificação: current_balance.'],
  ] as const)('a lookup that failed reads as one sentence in %s, without the English message (%#)', (locale, texts, sentence) => {
    panel(ticket('open', texts), locale)
    expect(screen.getByText(sentence, { exact: false })).toBeTruthy() // the reason shares its line with the rule
    const page = document.body.textContent ?? ''
    for (const raw of ['PRD-AB12CD34EF56', 'bank.duckdb', 'C:/srv', 'balance missing', 'Cannot open file', 'Tool failure', 'Data needed']) expect(page).not.toContain(raw)
  })

  it('a missing data with no field named reads without a placeholder', () => {
    const unspecified = { ...missing, reason_code: { code: 'data_unavailable_unspecified', params: {} } }
    panel(ticket('open', unspecified), 'es')
    expect(screen.getByText('Falta un dato necesario para responder con verificación.', { exact: false })).toBeTruthy()
    expect(document.body.textContent).not.toContain('balance missing')
  })

  it('the evidence type, the keys of the facts and the review reason are written too', async () => {
    panel(ticket('open', { ...english, ...codes }), 'es')
    await unfold(/^Evidencia/)
    await unfold(/^Hechos verificados/)
    expect(screen.getByRole('heading', { name: 'Pedido denegado · P-9' })).toBeTruthy()
    expect(within(block('Hechos verificados')).getByText(/^Herramienta: get_payment_status · Resultado: /)).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Rastrear movimiento' })).getByText('Pendiente desde hace más tiempo del que admite un rastreo simple').getAttribute('title')).toBe('older_than_review_threshold')
  })

  it.each(['es', 'pt'] as const)('a case filed before the codes shows the English text as it came (%s)', async (locale) => {
    panel(ticket('open', english), locale)
    await unfold(/^(Preguntas abiertas|Perguntas em aberto)/)
    expect(screen.getByText(english.reason, { exact: false })).toBeTruthy()
    for (const question of english.open_questions) expect(screen.getByText(question)).toBeTruthy()
    expect(screen.getByText(english.suggested_next_step)).toBeTruthy()
  })

  it('a code the console does not know shows the English text, question by question', async () => {
    const odd: typeof codes = { reason_code: { code: 'from_the_future' }, open_question_codes: [null, { code: 'also_new', params: {} }], next_step_code: 'nobody_knows_me' }
    panel(ticket('open', { ...english, ...odd }), 'es')
    await unfold(/^Preguntas abiertas/)
    expect(screen.getByText(english.reason, { exact: false })).toBeTruthy()
    for (const question of english.open_questions) expect(screen.getByText(question)).toBeTruthy()
    expect(screen.getByText(english.suggested_next_step)).toBeTruthy()
  })

  it('the summary the operator copies is in their language too', async () => {
    const user = userEvent.setup() // installs its own clipboard, which the panel writes to
    panel(ticket('claimed', { ...english, ...codes }, { operator: 'ana.ruiz', version: 1 }), 'pt')
    await user.click(screen.getByRole('button', { name: /Copiar resumo/ }))
    const summary = await navigator.clipboard.readText()
    expect(summary).toContain('Motivo: O cliente confirmou um rastreio')
    expect(summary).toContain('Próximo passo: Revisar a movimentação')
  })
})

// A case that arrives without a priority or a language is drawn, and says so: the header does not break and does not invent them.
describe('a case without priority or language', () => {
  it.each([['es', 'Desconocida', 'Desconocido'], ['pt', 'Desconhecida', 'Desconhecido']] as const)('is drawn and marked (%s)', (locale, priority, language) => {
    const incomplete = ticket('open', { priority: undefined, language: undefined })
    renderWithI18n(<TicketPanel ticket={incomplete} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} />, locale)
    expect(screen.getByText(priority).className).toContain('ui-priority--unknown')
    expect(screen.getByText(new RegExp(`MX · ${language}`))).toBeTruthy()
    expect(screen.getByText(`“${incomplete.request}”`)).toBeTruthy()
  })

  it('the summary does not print "undefined"', async () => {
    const user = userEvent.setup()
    renderWithI18n(<TicketPanel ticket={ticket('claimed', { priority: null }, { operator: 'ana.ruiz', version: 1 })} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} />)
    await user.click(screen.getByRole('button', { name: /Copiar resumen/ }))
    const summary = await navigator.clipboard.readText()
    expect(summary).toContain('Prioridad: Desconocida')
    expect(summary).not.toContain('undefined')
  })
})

describe('the customer segment in the header', () => {
  const header = () => document.querySelector('.op-ticket__state')!.textContent
  it.each([
    ['es', 'Student', 'Estudiante'],
    ['es', 'Basic', 'Básico'],
    ['pt', 'Student', 'Estudante'],
    ['pt', 'Basic', 'Básico'],
    ['es', 'Premium', 'Premium'],
    ['pt', 'Plus', 'Plus'],
  ] as const)('is said in the language of the operator (%s: %s)', (locale, segment, said) => {
    const t = ticket('open', { segment })
    renderWithI18n(<TicketPanel ticket={t} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} />, locale)
    expect(header()).toContain(` · ${said}`)
    if (said !== segment) expect(header()).not.toContain(segment)
  })

  it('a segment the console does not know is shown as it came', () => {
    setup(ticket('open', { segment: 'Retail' }))
    expect(header()).toContain(' · Retail')
  })
})

// The drawer reads summary first: the request and what to do, what needs attention, and the rest folded away with a line each.
describe('the drawer, summary first', () => {
  const customer = (over: Partial<CustomerContext> = {}): CustomerContext => ({
    warehouse: { available: true, as_of: '2026-06-01' },
    products: [
      { product_id: 'PRD-1', type: 'Cuenta Ahorro', currency: 'USD', status: 'Blocked', last4: '7547' },
      { product_id: 'PRD-2', type: 'Tarjeta Débito', currency: 'USD', status: 'Active', last4: '0002' },
    ],
    movements: [
      { transaction_id: 'TXN-9', date: '2026-08-12T03:39:00', product_id: 'PRD-1', type: 'Withdrawal', amount: 366.78, currency: 'USD', merchant: null, status: 'Pending', pending: true },
      { transaction_id: 'TXN-8', date: '2026-05-28T16:42:00', product_id: 'PRD-2', type: 'Transfer', amount: 6409.61, currency: 'USD', merchant: null, status: 'Approved', pending: false },
    ],
    pending_omitted: 0,
    cases: [],
    traces: [],
    ...over,
  })
  const quiet = customer({ products: [{ product_id: 'PRD-2', type: 'Tarjeta Débito', currency: 'USD', status: 'Active', last4: '0002' }], movements: [] })
  const loading = (context: CustomerContext) => ({ loadContext: vi.fn(async () => ({ ok: true as const, data: context })) })
  const attention = () => screen.queryByRole('region', { name: 'Requiere atención' })
  const folds = () => screen.getByRole('region', { name: 'Secciones' })
  const closedCase = () => ticket('resolved', { pending_action: null }, { operator: 'ana', version: 2, message: 'Te devolvimos el importe.', history: [{ action: 'resolve', status: 'resolved', operator: 'ana', ts: NOW - 120, detail: { message: 'Te devolvimos el importe.' } }] })

  it('starts with the request and the suggested next step in one card, with the reason in gray below the request', () => {
    setup(ticket('open', { prior_requests: ['Quiero saber el estado.'] }))
    const card = screen.getByRole('region', { name: 'Solicitud' })
    expect(within(card).getByText('“Hice un pago que sigue pendiente y quiero que lo rastreen.”')).toBeTruthy()
    expect(within(card).getByText(/ · regla /)).toBeTruthy()
    expect(within(card).getByText('Solicitudes anteriores')).toBeTruthy()
    expect(within(card).getByText('Quiero saber el estado.')).toBeTruthy()
    expect(within(card).getByText('Próximo paso sugerido')).toBeTruthy()
    expect(within(card).getByText('Llamar al cliente.')).toBeTruthy()
  })

  it('every section starts closed and says on its line what is inside', async () => {
    setup(ticket('claimed', { evidence: [{ type: 'transaction', id: 'tx1', flagged: true, detail: { transaction_date: '2026-09-28T14:02:00', amount: 199, currency: 'USD', merchant_name: 'Amazon MX', fraud_score: 91 } }] }, { version: 1, history: [{ action: 'claim', status: 'claimed', operator: 'ana.ruiz', ts: NOW - 60, detail: {} }] }), undefined, {
      ...loading(customer({ cases: [{ ticket_id: 'b2', category: 'fraud', queue: 'q', priority: 'Low', created_at: NOW - 100, status: 'open' }, { ticket_id: 'b3', category: 'fraud', queue: 'q', priority: 'Low', created_at: NOW - 100, status: 'approved' }] })),
    })
    await within(folds()).findByRole('button', { name: /^Productos/ })
    const summary = (name: RegExp) => within(folds()).getByRole('button', { name }).textContent
    expect(summary(/^Productos/)).toContain('2 · 1 bloqueado')
    expect(summary(/^Movimientos/)).toContain('1 pendiente')
    expect(summary(/^Evidencia/)).toBe('Evidencia1 · 1 marcado')
    expect(summary(/^Hechos verificados/)).toContain('1')
    expect(summary(/^Otros casos/)).toContain('2 · 1 abierto')
    expect(summary(/^Preguntas abiertas/)).toContain('1')
    expect(summary(/^Historial/)).toContain('2 eventos · traza')
    expect(within(folds()).getByText('Rastreos').closest('.op-fold')?.textContent).toContain('Ninguno')
    for (const fold of within(folds()).getAllByRole('button')) expect(fold.getAttribute('aria-expanded')).toBe('false')
    // Closed means closed: nothing of what is inside is in the page.
    expect(screen.queryByRole('list', { name: 'Movimientos recientes del cliente' })).toBeNull()
    expect(screen.queryByText('Tarjeta de débito')).toBeNull()
    expect(screen.queryByText('¿Autorizó el cliente el cargo?')).toBeNull()
  })

  it('a section opens and closes with the keyboard, and stays open while the same ticket is on screen', async () => {
    const user = userEvent.setup()
    const t = ticket('claimed', {}, { version: 1 })
    const view = { canAct: true, operator: 'ana.ruiz' }
    const act = vi.fn<TicketPanelProps['act']>(async () => ({ ok: true, data: t.desk }))
    const reload = vi.fn(async () => true)
    const { rerender } = renderWithI18n(<TicketPanel ticket={t} view={view} act={act} reload={reload} />)
    const fold = () => screen.getByRole('button', { name: /^Preguntas abiertas/ })
    // Tab walks to it: the sections are buttons, in the order of the page.
    for (let i = 0; i < 20 && document.activeElement !== fold(); i += 1) await user.tab()
    expect(document.activeElement).toBe(fold())
    await user.keyboard('{Enter}')
    expect(fold().getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('¿Autorizó el cliente el cargo?')).toBeTruthy()
    expect(fold().getAttribute('aria-controls')).toBe(screen.getByText('¿Autorizó el cliente el cargo?').closest('.op-fold__body')?.id)
    // The case is read again (a new version of the same ticket): what was open stays open.
    rerender(<I18nProvider locale="es" messages={dictionaries.es}><TicketPanel ticket={ticket('claimed', {}, { version: 2 })} view={view} act={act} reload={reload} /></I18nProvider>)
    expect(fold().getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('¿Autorizó el cliente el cargo?')).toBeTruthy()
    await user.keyboard(' ')
    expect(fold().getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('¿Autorizó el cliente el cargo?')).toBeNull()
  })

  it('another ticket starts closed again', async () => {
    const view = { canAct: true, operator: 'ana.ruiz' }
    const props = { view, act: vi.fn(), reload: vi.fn(async () => true) }
    const { rerender } = renderWithI18n(<TicketScreen ticketId="a91f3c00" result={{ ok: true, data: ticket('claimed', {}, { version: 1 }) }} {...props} />)
    await userEvent.setup().click(screen.getByRole('button', { name: /^Preguntas abiertas/ }))
    expect(screen.getByRole('button', { name: /^Preguntas abiertas/ }).getAttribute('aria-expanded')).toBe('true')
    rerender(<I18nProvider locale="es" messages={dictionaries.es}><TicketScreen ticketId="b2" result={{ ok: true, data: ticket('claimed', { ticket_id: 'b2' }, { version: 1 }) }} {...props} /></I18nProvider>)
    expect(screen.getByRole('button', { name: /^Preguntas abiertas/ }).getAttribute('aria-expanded')).toBe('false')
  })

  it('"Rastreos" without data is dimmed and cannot be opened', async () => {
    setup(ticket('open'), undefined, loading(customer()))
    await within(folds()).findByRole('button', { name: /^Productos/ })
    expect(within(folds()).queryByRole('button', { name: /^Rastreos/ })).toBeNull()
    const row = within(folds()).getByText('Rastreos').closest('.op-fold') as HTMLElement
    expect(row.hasAttribute('data-empty')).toBe(true)
    expect(row.textContent).toContain('Ninguno')
    await userEvent.setup().click(within(row).getByText('Rastreos'))
    expect(row.querySelector('.op-fold__body')).toBeNull()
  })

  it('"Requiere atención" gathers the pending movements and the products that are not active', async () => {
    setup(ticket('open'), undefined, loading(customer()))
    const card = await screen.findByRole('region', { name: 'Requiere atención' })
    const rows = within(card).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('Retiro pendiente')
    expect(rows[0].textContent).toContain('366.78 USD')
    expect(rows[0].textContent).toContain('08-12 03:39')
    expect(rows[1].textContent).toContain('Cuenta de ahorro ··7547')
    expect(rows[1].textContent).toContain('Bloqueado')
    expect(within(rows[1]).getByText('Terminada en 7547').className).toContain('sr-only')
  })

  it('"Requiere atención" also takes the movements the assistant flagged', () => {
    const flagged = { type: 'transaction', id: 'tx1', flagged: true, detail: { transaction_date: '2026-09-28T14:02:00', amount: 199, currency: 'USD', merchant_name: 'Amazon MX', fraud_score: 91 } }
    setup(ticket('open', { evidence: [flagged, { ...flagged, id: 'tx2', flagged: false, detail: { ...flagged.detail, fraud_score: 8 } }] }))
    const rows = within(attention()!).getAllByRole('listitem')
    expect(rows).toHaveLength(1)
    expect(rows[0].textContent).toContain('Movimiento marcado')
    expect(rows[0].textContent).toContain('199.00 USD')
    expect(rows[0].textContent).toContain('Amazon MX')
    expect(rows[0].textContent).toContain('score 91 del banco (no es de un modelo propio)')
  })

  it.each([
    ['nothing pending, blocked or flagged', quiet],
    ['no customer context at all', undefined],
  ])('"Requiere atención" is not drawn with %s', async (_, context) => {
    setup(ticket('open'), undefined, context ? loading(context) : {})
    if (context) await within(folds()).findByRole('button', { name: /^Productos/ })
    expect(attention()).toBeNull()
    expect(screen.queryByText('Requiere atención')).toBeNull()
  })

  it('"Requiere atención" is not drawn when the warehouse is down: it does not guess what it cannot read', async () => {
    setup(ticket('open'), undefined, loading(customer({ warehouse: { available: false, as_of: null }, products: [], movements: [] })))
    await screen.findByText('Los productos y movimientos del cliente no están disponibles ahora.')
    expect(attention()).toBeNull()
  })

  it('the forms and the pending action sit between "Requiere atención" and the sections, unfolded', async () => {
    setup(ticket('claimed', {}, { version: 1 }), undefined, loading(customer()))
    await screen.findByRole('region', { name: 'Requiere atención' })
    const order = [attention()!, screen.getByRole('region', { name: 'Rastrear movimiento' }), screen.getByLabelText(/Motivo del rechazo/), folds()]
    order.slice(1).forEach((el, i) => expect(order[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy())
    expect(screen.getByLabelText(/Motivo del rechazo/).closest('.op-folds')).toBeNull()
  })

  it('a closed case shows how it ended inside the summary, with the message of the operator', () => {
    setup(closedCase())
    const card = screen.getByRole('region', { name: 'Solicitud' })
    const outcome = within(card).getByRole('status')
    expect(outcome.textContent).toContain('Caso resuelto')
    expect(outcome.textContent).toContain('Mensaje de ana: “Te devolvimos el importe.”')
    const position = (el: Element) => card.innerHTML.indexOf(el.outerHTML)
    expect(position(outcome)).toBeLessThan(position(within(card).getByText('Próximo paso sugerido')))
    expect(position(within(card).getByText(/^“Hice un pago/))).toBeLessThan(position(outcome))
  })

  it('a closed case without a message still says how it ended, and the footer keeps its notes', () => {
    setup(ticket('rejected', {}, { operator: 'ana', version: 2, history: [{ action: 'reject', status: 'rejected', operator: 'ana', ts: NOW - 60, detail: {} }] }))
    expect(within(screen.getByRole('region', { name: 'Solicitud' })).getByText('Caso rechazado')).toBeTruthy()
    expect(screen.getByText('Cerrado · sin más acciones')).toBeTruthy()
    expect(button(/Copiar resumen/)).toBeTruthy()
  })

  it('the history opens onto the events, the trace and the session, and what the assistant did', async () => {
    setup(ticket('claimed', { actions_taken: [{ tool: 'get_payment_status' }] }, { version: 1, history: [{ action: 'claim', status: 'claimed', operator: 'ana.ruiz', ts: NOW - 60, detail: {} }] }))
    await unfold(/^Historial/)
    const body = screen.getByRole('button', { name: /^Historial/ }).closest('.op-fold')!
    expect(within(body as HTMLElement).getByText('Derivado por la asistente')).toBeTruthy()
    expect(within(body as HTMLElement).getByText('traza trace-12')).toBeTruthy()
    expect(within(body as HTMLElement).getByText('sesión sess-7e2')).toBeTruthy()
    expect(within(body as HTMLElement).getByText('Lo que hizo la asistente')).toBeTruthy()
    expect(within(body as HTMLElement).getByText('get_payment_status')).toBeTruthy()
  })

  it.each([
    ['es', 1, '1 · 1 marcado', '1 marcado · score 70+'],
    ['es', 2, '2 · 2 marcados', '2 marcados · score 70+'],
    ['pt', 1, '1 · 1 sinalizada', '1 sinalizada · score 70+'],
    ['pt', 2, '2 · 2 sinalizadas', '2 sinalizadas · score 70+'],
  ] as const)('the flagged movements agree in number with the count (%s, %i)', async (locale, count, line, body) => {
    const evidence = Array.from({ length: count }, (_, i) => ({ type: 'transaction', id: `tx${i}`, flagged: true, detail: { transaction_date: '2026-09-28T14:02:00', amount: 1, currency: 'USD', merchant_name: 'Amazon MX', fraud_score: 91 } }))
    renderWithI18n(<TicketPanel ticket={ticket('open', { evidence })} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} />, locale)
    const fold = screen.getByRole('button', { name: /^Evid/ })
    expect(fold.textContent).toContain(line)
    await userEvent.setup().click(fold)
    expect(screen.getByText(body)).toBeTruthy()
  })

  it('draws in Portuguese too', async () => {
    renderWithI18n(<TicketPanel ticket={ticket('open')} view={{ canAct: true, operator: 'ana.ruiz' }} act={vi.fn()} reload={vi.fn(async () => true)} loadContext={async () => ({ ok: true, data: customer() })} />, 'pt')
    expect(await screen.findByRole('region', { name: 'Requer atenção' })).toBeTruthy()
    expect(screen.getByText('Saque pendente')).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Seções' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^Produtos/ }).textContent).toContain('2 · 1 bloqueado')
    expect(screen.getByRole('button', { name: /^Histórico/ }).textContent).toContain('1 evento · rastro')
  })
})
