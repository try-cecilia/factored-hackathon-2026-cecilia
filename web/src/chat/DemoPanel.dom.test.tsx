import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { loadMessages, areasOf } from '../i18n/areas'
import { I18nProvider } from '../i18n/context'
import type { Locale } from '../i18n/locales'
import { renderWithI18n } from '../test/render'
import { DemoPanel } from './DemoPanel'
import type { DemoScenario } from './types'

const tickets = vi.hoisted(() => ({ list: [] as unknown[], traces: [] as unknown[], asked: 0 }))
vi.mock('../server/demo.functions', () => ({
  applyDemoFault: vi.fn(),
  getDemoTickets: async () => { tickets.asked += 1; return tickets.list },
  getDemoTraces: async () => tickets.traces,
  startScenario: vi.fn(),
}))

const scenario: DemoScenario = {
  id: 'normal_balance', path: 'normal', customer_id: 'CLI-FIX0001', language: 'es', fault: null, turns: ['¿Cuál es mi saldo?'], expect: ['AUTO_RESOLVE'],
  title: { en: 'Balance question', es: 'Consulta de saldo', pt: 'Consulta de saldo (PT)' },
  look_for: { en: 'Answered from verified data.', es: 'Se responde con datos verificados.', pt: 'Respondida com dados verificados.' },
}

const draw = (locale: 'es' | 'pt', scenarios = [scenario]) =>
  renderWithI18n(<DemoPanel scenarios={scenarios} sessionRef="s" entries={[]} pending={false} escalations={0} open ended={false} send={async () => null} onSend={() => () => {}} retry={() => {}} overlay={false} onSessionChanged={async () => {}} onClose={() => {}} />, locale)

// The page the customer gets: the texts of the customer area only, as the root loader resolves them, and not the console's.
async function drawAsCustomer(locale: Locale, open = true) {
  const messages = await loadMessages(areasOf('/chat'), locale)
  return render(
    <I18nProvider locale={locale} messages={messages}>
      <DemoPanel scenarios={[scenario]} sessionRef="s" entries={[]} pending={false} escalations={0} open={open} ended={false} send={async () => null} onSend={() => () => {}} retry={() => {}} overlay={false} onSessionChanged={async () => {}} onClose={() => {}} />
    </I18nProvider>,
  )
}

describe('DemoPanel', () => {
  it('shows each scenario in the language of the interface', () => {
    draw('pt')
    expect(screen.getByText('Consulta de saldo (PT)')).toBeTruthy()
    expect(screen.getByText('Respondida com dados verificados.')).toBeTruthy()
  })

  it('in Spanish it shows the Spanish', () => {
    draw('es')
    expect(screen.getByText('Consulta de saldo')).toBeTruthy()
    expect(screen.getByText('Se responde con datos verificados.')).toBeTruthy()
  })

  it('an API that predates Portuguese falls back to Spanish instead of showing nothing', () => {
    const old = { ...scenario, title: { en: 'x', es: 'Consulta de saldo' }, look_for: { en: 'x', es: 'Se responde.' } }
    draw('pt', [old])
    expect(screen.getByText('Consulta de saldo')).toBeTruthy()
  })

  describe('the bank view, as the agent receives the ticket, in the language of the interface', () => {
    const coded = {
      ticket_id: 'T-0123456789', queue: 'fraud_ops', priority: 'Critical', category: 'fraud',
      request: 'No reconozco un cargo',
      reason: 'Safety signal in the request: fraud.', reason_code: { code: 'safety_signal', params: { categories: 'fraud' } },
      open_questions: ["Confirm whether the customer's card/account must be blocked.", 'Verify identity with a stronger factor before acting.'],
      open_question_codes: [{ code: 'confirm_block' }, { code: 'verify_identity' }],
      suggested_next_step: 'Call the customer back on the registered number; block the card if confirmed; open a dispute case.', next_step_code: 'fraud',
      created_at: 1,
    }
    it('in Spanish the reason, the questions, the next step and the priority are Spanish', async () => {
      tickets.list = [coded]
      await drawAsCustomer('es')
      const card = within((await screen.findByText('fraud_ops')).closest('article') as HTMLElement)
      expect(card.getByText('Crítica')).toBeTruthy()
      expect(card.getByText(/Señal de seguridad en el pedido: Fraude/)).toBeTruthy()
      expect(card.getByText(/Confirmar si hay que bloquear la tarjeta/)).toBeTruthy()
      expect(card.getByText(/Llamar al cliente al número registrado/)).toBeTruthy()
      expect(card.queryByText(/Safety signal|Critical|Call the customer|Confirm whether/)).toBeNull()
    })

    it('in Portuguese too', async () => {
      tickets.list = [coded]
      await drawAsCustomer('pt')
      const card = within((await screen.findByText('fraud_ops')).closest('article') as HTMLElement)
      expect(card.getByText('Crítica')).toBeTruthy()
      expect(card.getByText(/Sinal de segurança no pedido/)).toBeTruthy()
      expect(card.queryByText(/Safety signal|Critical|Call the customer|Confirm whether/)).toBeNull()
    })

    it('a ticket without codes, or with one the console does not know, shows its text as it came', async () => {
      tickets.list = [{ ...coded, priority: 'Urgente', reason_code: { code: 'a_new_reason' }, open_question_codes: undefined, next_step_code: null }]
      await drawAsCustomer('es')
      const card = within((await screen.findByText('fraud_ops')).closest('article') as HTMLElement)
      expect(card.getByText('Safety signal in the request: fraud.')).toBeTruthy()
      expect(card.getByText(/Call the customer back/)).toBeTruthy()
      expect(card.getByText('Desconocida')).toBeTruthy()
    })
  })

  describe('the bank view lists the trace requests this session opened, as operations receives them', () => {
    const trace = { trace_id: 'TR-15B5F466D9D65B60', transaction_id: 'TXN-FIX0006', queue: 'payments_ops', status: 'open', sla_business_days: 2, created_at: 1 }

    it('in Spanish: the number, the movement, the state and the term, and not the empty note', async () => {
      tickets.list = []
      tickets.traces = [trace]
      await drawAsCustomer('es')
      const card = within((await screen.findByText('TR-15B5F466D9D65B60')).closest('article') as HTMLElement)
      expect(card.getByText('payments_ops')).toBeTruthy()
      expect(card.getByText('TXN-FIX0006')).toBeTruthy()
      expect(card.getByText('Abierto')).toBeTruthy()
      expect(card.getByText('2 días hábiles')).toBeTruthy()
      expect(screen.getByText('Pedidos de rastreo')).toBeTruthy()
      expect(screen.queryByText(/Todavía no hay casos/)).toBeNull()
    })

    it('in Portuguese too', async () => {
      tickets.list = []
      tickets.traces = [{ ...trace, sla_business_days: 1 }]
      await drawAsCustomer('pt')
      const card = within((await screen.findByText('TR-15B5F466D9D65B60')).closest('article') as HTMLElement)
      expect(card.getByText('Aberto')).toBeTruthy()
      expect(card.getByText('1 dia útil')).toBeTruthy()
      expect(screen.getByText('Pedidos de rastreamento')).toBeTruthy()
    })

    it('with neither a ticket nor a trace the bank view says there is nothing yet', async () => {
      tickets.list = []
      tickets.traces = []
      await drawAsCustomer('es')
      expect(await screen.findByText(/Todavía no hay casos/)).toBeTruthy()
    })
  })

  describe('nothing of the bank view is asked for until the panel is shown', () => {
    it('a panel that is not on screen asks for nothing, and asks when it is shown', async () => {
      tickets.list = []
      tickets.traces = []
      tickets.asked = 0
      const messages = await loadMessages(areasOf('/chat'), 'es')
      const panel = (open: boolean) => (
        <I18nProvider locale="es" messages={messages}>
          <DemoPanel scenarios={[scenario]} sessionRef="s" entries={[]} pending={false} escalations={0} open={open} ended={false} send={async () => null} onSend={() => () => {}} retry={() => {}} overlay onSessionChanged={async () => {}} onClose={() => {}} />
        </I18nProvider>
      )
      const view = render(panel(false))
      await new Promise((resolve) => setTimeout(resolve, 50))
      expect(tickets.asked).toBe(0)
      view.rerender(panel(true))
      await screen.findByText(/Todavía no hay casos/)
      expect(tickets.asked).toBeGreaterThan(0)
    })
  })
})
