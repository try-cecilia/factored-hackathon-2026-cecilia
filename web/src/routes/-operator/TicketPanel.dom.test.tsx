import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DeskState, DeskStatus, Ticket } from '../../server/operator.functions'
import { I18nProvider } from '../../i18n/context'
import { renderWithI18n, dictionaries } from '../../test/render'
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

// What the operator reads of the assistant's own decision: written from the codes of the case, in the operator's language, and the
// English text of the API wherever the case has no code (or one this console does not know).
describe('the texts of the case', () => {
  const english = {
    reason: 'The customer confirmed a trace, but the movement needs a person\'s approval (older_than_review_threshold).',
    policy_rule: 'action:trace_review',
    open_questions: ['Approve or reject the trace: older_than_review_threshold.', 'Could not gather recent activity automatically: db down'],
    suggested_next_step: 'Review the movement (see pending_action.review_reason) and approve or reject the trace the customer asked for.',
    verified_facts: [{ tool: 'get_payment_status', result: { status: 'pending' } }],
    evidence: [{ type: 'denied_request', id: 'P-9', detail: { tool: 'get_account_summary' } }],
  }
  const codes: Pick<Ticket, 'reason_code' | 'open_question_codes' | 'next_step_code'> = {
    reason_code: { code: 'trace_review', params: { review_reason: 'older_than_review_threshold' } },
    open_question_codes: [{ code: 'decide_trace', params: { review_reason: 'older_than_review_threshold' } }, { code: 'evidence_failed', params: { detail: 'db down' } }],
    next_step_code: 'trace_review',
  }
  const view = { canAct: true, operator: 'ana.ruiz' }
  const panel = (t: Ticket, locale: 'es' | 'pt') =>
    renderWithI18n(<TicketPanel ticket={t} view={view} act={vi.fn()} reload={vi.fn(async () => true)} />, locale)
  const block = (heading: string) => screen.getByRole('heading', { name: heading }).closest('section') as HTMLElement

  it('in Spanish, from the codes', () => {
    panel(ticket('open', { ...english, ...codes }), 'es')
    expect(screen.getByText(/^El cliente confirmó un rastreo, pero el movimiento necesita la aprobación de una persona \(Pendiente desde hace más tiempo/)).toBeTruthy()
    expect(screen.getByText(/regla Rastreo: lo decide una persona$/)).toBeTruthy()
    const questions = within(block('Preguntas abiertas')).getAllByRole('listitem').map((li) => li.textContent)
    expect(questions).toEqual(['Aprobar o rechazar el rastreo: Pendiente desde hace más tiempo del que admite un rastreo simple.', 'No se pudo reunir la actividad reciente automáticamente: db down'])
    expect(within(block('Próximo paso sugerido')).getByText(/^Revisar el movimiento \(ver el motivo de revisión\)/)).toBeTruthy()
    expect(screen.queryByText(/Approve or reject|Review the movement|Could not gather/)).toBeNull()
  })

  it('in Portuguese, from the codes', () => {
    panel(ticket('open', { ...english, ...codes }), 'pt')
    expect(screen.getByText(/^O cliente confirmou um rastreio, mas a movimentação precisa da aprovação de uma pessoa/)).toBeTruthy()
    const questions = within(block('Perguntas em aberto')).getAllByRole('listitem').map((li) => li.textContent)
    expect(questions).toEqual(['Aprovar ou rejeitar o rastreio: Pendente há mais tempo do que um rastreio simples admite.', 'Não foi possível reunir a atividade recente automaticamente: db down'])
    expect(within(block('Próximo passo sugerido')).getByText(/^Revisar a movimentação/)).toBeTruthy()
  })

  it('the evidence type, the keys of the facts and the review reason are written too', () => {
    panel(ticket('open', { ...english, ...codes }), 'es')
    expect(screen.getByRole('heading', { name: 'Pedido denegado · P-9' })).toBeTruthy()
    expect(within(block('Hechos verificados')).getByText(/^Herramienta: get_payment_status · Resultado: /)).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Rastrear movimiento' })).getByText('Pendiente desde hace más tiempo del que admite un rastreo simple').getAttribute('title')).toBe('older_than_review_threshold')
  })

  it.each(['es', 'pt'] as const)('a case filed before the codes shows the English text as it came (%s)', (locale) => {
    panel(ticket('open', english), locale)
    expect(screen.getByText(english.reason, { exact: false })).toBeTruthy()
    for (const question of english.open_questions) expect(screen.getByText(question)).toBeTruthy()
    expect(screen.getByText(english.suggested_next_step)).toBeTruthy()
  })

  it('a code the console does not know shows the English text, question by question', () => {
    const odd: typeof codes = { reason_code: { code: 'from_the_future' }, open_question_codes: [null, { code: 'also_new', params: {} }], next_step_code: 'nobody_knows_me' }
    panel(ticket('open', { ...english, ...odd }), 'es')
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
    expect(screen.getByText(incomplete.request)).toBeTruthy()
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
