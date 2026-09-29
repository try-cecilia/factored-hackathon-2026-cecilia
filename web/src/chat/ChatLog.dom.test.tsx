import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithI18n } from '../test/render'
import { ChatLog, type ChatLogProps } from './ChatLog'
import type { Entry } from './conversation'
import type { Reply } from './types'

let id = 0
const reply = (over: Partial<Reply> = {}): Reply => ({
  trace_id: 'abc12345', disposition: 'AUTO_RESOLVE', response_text: 'Tu saldo es 10 USD.', language: 'es', category: 'resolved', ticket_id: null, latency_ms: 1, ...over,
})
const user = (text: string, over: Partial<Extract<Entry, { role: 'user' }>> = {}): Entry => ({ id: ++id, role: 'user', text, at: 1, key: 'k', delivery: 'sent', ...over })
const assistant = (r: Reply): Entry => ({ id: ++id, role: 'assistant', reply: r, at: 2 })

function setup(entries: Entry[], over: Partial<ChatLogProps> = {}) {
  const props: ChatLogProps = {
    entries, cases: [], sending: false, live: true, ended: false,
    onSend: vi.fn(), onRetry: vi.fn(), onReload: vi.fn(), onViewCase: vi.fn(), onSignIn: vi.fn(), ...over,
  }
  renderWithI18n(<ChatLog {...props} />, 'es')
  return props
}

const proposal = reply({ disposition: 'CLARIFY', category: 'confirm_action', response_text: 'Encontré este movimiento pendiente. ¿Quieres que abra un pedido de rastreo? Responde sí o no.' })

describe('ChatLog', () => {
  it('draws an answer as open text, with "¿Por qué?" only when the API sent the demo explanation', () => {
    setup([user('saldo'), assistant(reply())])
    expect(screen.getByText('Tu saldo es 10 USD.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /¿Por qué\?/ })).toBeNull()
  })

  it('shows "¿Por qué?" in the demo, with the facts the API explained', async () => {
    const why = {
      rule: 'verified_tool_results', because: { en: 'x', es: 'Datos verificados' },
      model: { called: true, provider: 'p', model: 'm', saw: 'saldo', chose: [{ tool: 'get_account_summary', args: {} }] },
      checks: [{ tool: 'get_account_summary', product: null, ok: true, outcome: 'ok' }], llm_calls: 1, cost_usd: 0, latency_ms: 12,
    }
    setup([assistant(reply({ why }))])
    const toggle = screen.getByRole('button', { name: /¿Por qué\?/ })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    await userEvent.setup().click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('Datos verificados')).toBeTruthy()
    expect(screen.getByText('verified_tool_results')).toBeTruthy()
  })

  it('a clarification offers its options; choosing one sends that answer and then locks the rest', async () => {
    const entries = [assistant(reply({ disposition: 'CLARIFY', category: 'x', response_text: '¿Sobre cuál de tus productos? 1) Cuenta Ahorro (USD); 2) Tarjeta (USD)' }))]
    const props = setup(entries)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Tarjeta (USD)' }))
    expect(props.onSend).toHaveBeenCalledWith('Tarjeta')
  })

  it('once a clarification is answered, the chosen option stays and the others stop answering', () => {
    setup([assistant(reply({ disposition: 'CLARIFY', category: 'x', response_text: '¿Sobre cuál? 1) Cuenta Ahorro (USD); 2) Tarjeta (USD)' })), user('Tarjeta')])
    expect(screen.getByRole('button', { name: 'Tarjeta (USD)' }).getAttribute('aria-pressed')).toBe('true')
    expect((screen.getByRole('button', { name: 'Cuenta Ahorro (USD)' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('a decline says what she can do, in chips', async () => {
    const props = setup([assistant(reply({ disposition: 'ABSTAIN', category: 'out_of_scope', response_text: 'Eso está fuera de lo que puedo resolver.' }))])
    await userEvent.setup().click(screen.getByRole('button', { name: '¿Cuál es mi saldo?' }))
    expect(props.onSend).toHaveBeenCalledWith('¿Cuál es mi saldo?')
  })

  it('a handoff reads the case back with its number and where it stands, and "Ver caso" brings it to the sidebar', async () => {
    const ticket = '55d09c14-2235-4c3c-8967-ccac61db9c50'
    const entries = [assistant(reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: ticket, response_text: 'Voy a transferir tu caso.' }))]
    const props = setup(entries, { cases: [{ ref: { ticketId: ticket, category: 'theft', at: 1 }, state: { state: 'ready', status: 'claimed', message: null } }] })
    const group = screen.getByRole('group', { name: 'Robo o clonación de tarjeta' })
    expect(group.textContent).toContain('En revisión')
    expect(within(group).getByText(`#${ticket}`)).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: /Ver caso/ }))
    expect(props.onViewCase).toHaveBeenCalledWith(ticket)
  })

  it('a handoff with no case number is "could not verify", retries by sending the customer\'s message again, and only while it is the last', async () => {
    const entries = [user('¿Cuánto debo?'), assistant(reply({ disposition: 'ESCALATE', category: 'tool_failure', ticket_id: null, response_text: 'No pude registrar tu caso.' }))]
    const props = setup(entries)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Intentar de nuevo' }))
    expect(props.onSend).toHaveBeenCalledWith('¿Cuánto debo?')
  })

  it('the proposal to trace waits for the customer\'s yes or no, in the language of the reply, and never sends while another message is in flight', async () => {
    const props = setup([assistant(proposal)])
    const user_ = userEvent.setup()
    await user_.click(screen.getByRole('button', { name: 'Sí, rastrear' }))
    await user_.click(screen.getByRole('button', { name: 'Ahora no' }))
    expect(vi.mocked(props.onSend).mock.calls).toEqual([['Sí'], ['No']])
  })

  it('a proposal that is no longer the last message, or whose session ended, offers no answer', () => {
    setup([assistant(proposal), user('otra cosa')])
    expect(screen.queryByRole('button', { name: 'Ahora no' })).toBeNull()
    expect(screen.getByText('Sin rastrear por ahora')).toBeTruthy()
  })

  it('the yes is followed by the action result, announced only after the API said so', () => {
    setup([assistant(proposal), user('Sí'), assistant(reply({ response_text: 'Listo: abrí el pedido de rastreo TR-1.' }))])
    expect(screen.getByText('Rastreo abierto')).toBeTruthy()
    expect(screen.getByText(/abrí el pedido de rastreo TR-1/)).toBeTruthy()
    expect(screen.getByText('Solicitud enviada')).toBeTruthy()
  })

  it('limited mode adds its banner above the reply', () => {
    setup([assistant(reply({ degraded: true }))])
    expect(screen.getByText(/Cecilia está limitada por ahora/)).toBeTruthy()
  })

  it('what a person did with a case comes out of the reply as a system note', () => {
    setup([assistant(reply({ response_text: 'Novedad de tu caso: un agente ya lo tomó y lo está revisando.\n\nTu saldo es 10 USD.' }))])
    expect(screen.getByText('Novedad de tu caso: un agente ya lo tomó y lo está revisando.').closest('.ui-note')).not.toBeNull()
    expect(screen.getByText('Tu saldo es 10 USD.')).toBeTruthy()
  })

  it('a send that may have been lost says so, keeps the message, and retries only when it is safe', async () => {
    const entries = [user('hola', { delivery: 'uncertain', failure: 'timeout' })]
    const props = setup(entries)
    expect(screen.getByText(/no pude confirmar si tu mensaje llegó/)).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(props.onRetry).toHaveBeenCalledWith(entries[0].id)
  })

  it('a message the API already has (409) offers to load the conversation, with the honest text', async () => {
    const props = setup([user('hola', { delivery: 'processed', failure: 'already_processed' })])
    expect(screen.getByText(/Cargar la conversación muestra su respuesta/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cargar la conversación' }))
    expect(props.onReload).toHaveBeenCalledOnce()
  })

  it('a refused send (rate limit) can be retried, but not once the session has ended', () => {
    const entries = [user('hola', { delivery: 'failed', failure: 'rate_limited' })]
    setup(entries, { ended: true })
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
  })

  it('a message on its way shows "Enviando", and the wait is three dots, not text arriving piece by piece', () => {
    setup([user('hola', { delivery: 'sending' })], { sending: true })
    expect(screen.getByText('Enviando')).toBeTruthy()
    expect(screen.getByText('Cecilia está pensando')).toBeTruthy()
  })

  it('when the session ended the log ends with the sign-in message', async () => {
    const props = setup([user('hola')], { ended: true })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Ingresar de nuevo' }))
    expect(props.onSignIn).toHaveBeenCalledOnce()
  })

  it('history restored from the API ends with a note that says the conversation was resumed', () => {
    setup([user('hola'), { id: ++id, role: 'note', note: 'restored', at: 0 }])
    expect(screen.getByText('Conversación retomada')).toBeTruthy()
  })
})
