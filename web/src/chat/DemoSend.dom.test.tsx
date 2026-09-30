import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Session } from '../server/auth.functions'
import type { DemoKit } from '../server/demo.functions'
import { AppShell } from '../shell/AppShell'
import { renderWithI18n } from '../test/render'
import { ChatView } from './ChatView'
import { ConversationProvider } from './ConversationProvider'
import type { DemoScenario, HistoryResult, Reply } from './types'

const router = vi.hoisted(() => ({ invalidate: async () => {} }))
const sendMessage = vi.hoisted(() => vi.fn())
const startScenario = vi.hoisted(() => vi.fn())
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...rest }: { to: string; children?: ReactNode }) => <a href={to} {...rest}>{children}</a>,
  useNavigate: () => vi.fn(),
  useRouter: () => ({ invalidate: () => router.invalidate() }),
}))
vi.mock('../server/auth.functions', () => ({ logout: vi.fn() }))
vi.mock('../server/locale.functions', () => ({ setLocale: vi.fn() }))
vi.mock('../server/demo.functions', () => ({ applyDemoFault: vi.fn(), getDemoTickets: async () => [], startScenario }))
const getHistory = vi.hoisted(() => vi.fn())
vi.mock('../server/chat.functions', () => ({ sendMessage, getHistory, getCase: vi.fn() }))

const scenario = (id: string, turns: string[], expect: (string | null)[], title: string): DemoScenario => ({
  id, path: 'normal', customer_id: 'CLI-FIX0001', language: 'es', fault: null, turns, expect,
  title: { en: title, es: title, pt: `${title} (PT)` }, look_for: { en: 'x', es: `Mirar ${title}` },
})
// The one that is chosen is the last of a long list: its card is below what the panel shows without scrolling.
const scenarios = [
  scenario('a', ['uno'], ['AUTO_RESOLVE'], 'Primero'),
  scenario('b', ['dos'], ['AUTO_RESOLVE'], 'Segundo'),
  scenario('c', ['tres'], ['AUTO_RESOLVE'], 'Tercero'),
  scenario('d', ['cuatro'], ['AUTO_RESOLVE'], 'Cuarto'),
  scenario('e', ['¿Cuál es mi saldo?', 'Me clonaron la tarjeta'], ['AUTO_RESOLVE', 'ESCALATE'], 'Dos turnos'),
]
// What the API kept of a session when its conversation is read: a test can make it fail.
const history = vi.hoisted(() => ({ initial: { ok: true, cases: [], turns: [] } as HistoryResult }))
const kit: Promise<DemoKit> = Promise.resolve({ enabled: true, scenarios })

const reply = (disposition: Reply['disposition'], text: string): Reply =>
  ({ trace_id: 'abc12345', disposition, response_text: text, language: 'es', category: 'resolved', ticket_id: null, latency_ms: 1 })

function phone(narrow: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: narrow && query.includes('1179px'), media: query, addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false, onchange: null,
  })) as unknown as typeof window.matchMedia
}

// A scenario signs in as another customer: the session changes when the route is invalidated, as it does in the app.
function App() {
  const [ref, setRef] = useState('s1')
  router.invalidate = async () => { setRef((r) => `${r}+`) }
  const session: Session = { customer_id: 'CLI-FIX0001', session_ref: ref, segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }
  return (
    <ConversationProvider sessionRef={ref} initial={history.initial}>
      <AppShell session={session} kit={kit}><ChatView session={session} /></AppShell>
    </ConversationProvider>
  )
}

// The route gives the shell its session before the loader gives the provider the session's history: for a moment the panel lives
// in the new session while the conversation is still the old one, which has turns of its own.
function LaggingApp() {
  const [shell, setShell] = useState('s1')
  const [conversation, setConversation] = useState('s1')
  router.invalidate = async () => {
    setShell((r) => `${r}+`)
    await new Promise((resolve) => setTimeout(resolve, 60))
    setConversation((r) => `${r}+`)
  }
  const session: Session = { customer_id: 'CLI-FIX0001', session_ref: shell, segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }
  const old = conversation === 's1'
  const turns = old
    ? [{ role: 'user' as const, text: 'algo de antes', at: 1 }, { role: 'assistant' as const, reply: reply('AUTO_RESOLVE', 'Respuesta de antes'), at: 2 }]
    : []
  return (
    <ConversationProvider sessionRef={conversation} initial={{ ok: true, cases: [], turns }}>
      <AppShell session={session} kit={kit}><ChatView session={session} /></AppShell>
    </ConversationProvider>
  )
}

async function draw(locale: 'es' | 'pt' = 'es') {
  let drawn: ReturnType<typeof renderWithI18n> | undefined
  await act(async () => { drawn = renderWithI18n(<App />, locale) })
  return drawn as ReturnType<typeof renderWithI18n>
}

const panel = () => screen.findByRole('complementary', { name: 'Ayudas de demostración' })
const input = () => screen.getByRole('textbox', { name: 'Mensaje para Cecilia' }) as HTMLTextAreaElement
async function load(user: ReturnType<typeof userEvent.setup>, title: string) {
  const card = within(await panel()).getByRole('article', { name: title })
  await user.click(within(card).getByRole('button', { name: /Cargar|Reiniciar/ }))
  return card
}

beforeEach(() => {
  phone(false)
  Element.prototype.scrollIntoView = vi.fn()
  globalThis.ResizeObserver = class { observe() {} disconnect() {} unobserve() {} } as unknown as typeof ResizeObserver
  startScenario.mockReset().mockResolvedValue({ ok: true })
  sendMessage.mockReset().mockReturnValue(new Promise(() => {}))
  getHistory.mockReset()
  history.initial = { ok: true, cases: [], turns: [] }
})
afterEach(() => vi.restoreAllMocks())

describe('a scenario of the demo panel sends its first message through the chat', () => {
  it('choosing a scenario far down the list sends its first message, which shows in the chat, and draws nothing above the list', async () => {
    const user = userEvent.setup()
    await draw()
    const aside = await panel()
    const before = within(aside).getAllByRole('region').map((r) => r.getAttribute('aria-label'))
    expect(before[0]).toBe('Escenarios guiados')

    const card = await load(user, 'Dos turnos')

    await waitFor(() => expect(sendMessage).toHaveBeenCalledOnce())
    expect(sendMessage.mock.calls[0][0].data).toMatchObject({ message: '¿Cuál es mi saldo?', key: expect.any(String) })
    expect(await screen.findByText('¿Cuál es mi saldo?')).toBeTruthy()
    expect(input().value).toBe('')
    // Its steps are in its own card, in its place; above the list there is still nothing but the scenarios.
    expect(within(card).getByRole('region', { name: 'Pasos del escenario' })).toBeTruthy()
    expect(within(aside).getAllByRole('region')[0].getAttribute('aria-label')).toBe('Escenarios guiados')
    expect(within(aside).getAllByRole('region', { name: 'Pasos del escenario' })).toHaveLength(1)
  })

  it('the first message waits for the conversation of the new session: it is not sent into the old one, and its reply is not lost', async () => {
    const user = userEvent.setup()
    sendMessage.mockResolvedValue({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await act(async () => { renderWithI18n(<LaggingApp />, 'es') })
    expect(screen.getByText('Respuesta de antes')).toBeTruthy()
    const card = await load(user, 'Dos turnos')

    expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
    expect(screen.queryByText('Respuesta de antes')).toBeNull()
    expect(screen.getByText('¿Cuál es mi saldo?')).toBeTruthy()
    expect(sendMessage).toHaveBeenCalledOnce()
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
  })

  it('the reply fills the step, and the next one waits in the card to be sent with a click, not in the input', async () => {
    const user = userEvent.setup()
    sendMessage.mockResolvedValue({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await draw()
    const card = await load(user, 'Dos turnos')

    expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
    expect(sendMessage).toHaveBeenCalledOnce()
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
    expect(input().value).toBe('')
    expect((within(card).getByRole('button', { name: 'Enviar paso 2' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('a click on the next step sends it through the chat and the second step is judged against what was expected', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      .mockResolvedValueOnce({ ok: true, reply: reply('CLARIFY', '¿Qué pasó exactamente?') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await user.click(await within(card).findByRole('button', { name: 'Enviar paso 2' }))

    expect(sendMessage).toHaveBeenCalledTimes(2)
    expect(sendMessage.mock.calls[1][0].data).toMatchObject({ message: 'Me clonaron la tarjeta', key: expect.any(String) })
    expect(sendMessage.mock.calls[1][0].data.key).not.toBe(sendMessage.mock.calls[0][0].data.key)
    expect(await within(card).findByText('✗ Salió Pregunta')).toBeTruthy()
    // The scenario is over: there is no step left to send, and the input was never written into.
    expect(within(card).queryByRole('button', { name: /^Enviar paso/ })).toBeNull()
    expect(input().value).toBe('')
  })

  it('a message the person is writing is not touched by the steps', async () => {
    const user = userEvent.setup()
    let answer: (value: unknown) => void = () => {}
    sendMessage.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(sendMessage).toHaveBeenCalledOnce())

    await user.type(input(), 'mi propio borrador')
    await act(async () => { answer({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') }) })
    expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
    expect(input().value).toBe('mi propio borrador')
  })

  it('a reply to a message that is not the step is not the step: the card says so and the scenario stays where it was', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'El dólar está a 17 pesos.') })
      .mockResolvedValueOnce({ ok: true, reply: reply('ESCALATE', 'Te paso con una persona.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await within(card).findByRole('button', { name: 'Enviar paso 2' })

    await user.type(input(), '¿A cuánto está el dólar?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))

    expect(await screen.findByText('El dólar está a 17 pesos.')).toBeTruthy()
    expect(within(card).getByRole('status', { name: '' }).textContent).toContain('no cuenta como paso')
    expect(within(card).queryByText(/^✗/)).toBeNull()

    // Back on the script, the step is answered and the note goes.
    await user.click(within(card).getByRole('button', { name: 'Enviar paso 2' }))
    expect(await within(card).findByText('✓ A una persona')).toBeTruthy()
    expect(sendMessage.mock.calls[2][0].data.message).toBe('Me clonaron la tarjeta')
    expect(within(card).queryByRole('status')).toBeNull()
  })

  it('a step whose message failed and was retried after other messages is answered by the retry, not lost', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'El dólar está a 17 pesos.') })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await screen.findByRole('button', { name: 'Reintentar' })
    await user.type(input(), '¿A cuánto está el dólar?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await screen.findByText('El dólar está a 17 pesos.')
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByText('Tu saldo es 10 USD.')

    expect(sendMessage.mock.calls[0][0].data.key).toBe(sendMessage.mock.calls[2][0].data.key)
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
    expect(within(card).queryByRole('status')).toBeNull()
    expect(within(card).getByRole('button', { name: 'Enviar paso 2' })).toBeTruthy()
  })

  it('the button of a step whose message did not get an answer retries that message, with its key, and does not send another', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await screen.findByRole('button', { name: 'Reintentar' })

    const retry = await within(card).findByRole('button', { name: 'Reintentar paso 1' })
    expect((retry as HTMLButtonElement).disabled).toBe(false)
    await user.click(retry)

    expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
    expect(sendMessage).toHaveBeenCalledTimes(2)
    expect(sendMessage.mock.calls[1][0].data.key).toBe(sendMessage.mock.calls[0][0].data.key)
    expect(screen.getAllByText('¿Cuál es mi saldo?')).toHaveLength(1)
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
    expect(within(card).getByRole('button', { name: 'Enviar paso 2' })).toBeTruthy()
  })

  it('a later step that did not get an answer is retried from its card with its key, too', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: true, reply: reply('ESCALATE', 'Te paso con una persona.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await user.click(await within(card).findByRole('button', { name: 'Enviar paso 2' }))
    await user.click(await within(card).findByRole('button', { name: 'Reintentar paso 2' }))

    expect(await screen.findByText('Te paso con una persona.')).toBeTruthy()
    expect(sendMessage).toHaveBeenCalledTimes(3)
    expect(sendMessage.mock.calls[2][0].data.key).toBe(sendMessage.mock.calls[1][0].data.key)
    expect(screen.getAllByText('Me clonaron la tarjeta')).toHaveLength(1)
    expect(await within(card).findByText('✓ A una persona')).toBeTruthy()
  })

  it('a history read that comes back empty does not make the card forget the message that was lost: its retry keeps the key', async () => {
    const user = userEvent.setup()
    history.initial = { ok: false, failure: 'unavailable' }
    getHistory.mockResolvedValue({ ok: true, cases: [], turns: [] })
    sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await within(card).findByRole('button', { name: 'Reintentar paso 1' })

    // The conversation could not be read: its notice offers to read it again, and what comes back does not have the message yet.
    await user.click(document.querySelector('.chat__history button') as HTMLElement)
    await waitFor(() => expect(getHistory).toHaveBeenCalled())

    await waitFor(() => expect(document.querySelector('.chat__history')).toBeNull())
    await user.click(within(card).getByRole('button', { name: 'Reintentar paso 1' }))
    expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
    expect(sendMessage).toHaveBeenCalledTimes(2)
    expect(sendMessage.mock.calls[1][0].data.key).toBe(sendMessage.mock.calls[0][0].data.key)
    expect(screen.getAllByText('¿Cuál es mi saldo?')).toHaveLength(1)
  })

  it('a reload whose window no longer holds a step that was confirmed does not take it back: it is not offered again, and the retry keeps its key', async () => {
    const user = userEvent.setup()
    history.initial = { ok: false, failure: 'unavailable' }
    // The API keeps the last 40 entries: what comes back is others' conversation, without the scenario's first step.
    const foreign = Array.from({ length: 20 }, (_, i) => [
      { role: 'user' as const, text: `ajena ${i}`, at: 2 * i },
      { role: 'assistant' as const, reply: reply('AUTO_RESOLVE', `respuesta ${i}`), at: 2 * i + 1 },
    ]).flat()
    getHistory.mockResolvedValue({ ok: true, cases: [], turns: foreign })
    sendMessage
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: true, reply: reply('ESCALATE', 'Te paso con una persona.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
    await user.click(await within(card).findByRole('button', { name: 'Enviar paso 2' }))
    await within(card).findByRole('button', { name: 'Reintentar paso 2' })

    await user.click(document.querySelector('.chat__history button') as HTMLElement)
    expect(await screen.findByText('ajena 19')).toBeTruthy()
    expect(screen.queryByText('Tu saldo es 10 USD.')).toBeNull()

    expect(within(card).queryByRole('button', { name: 'Enviar paso 1' })).toBeNull()
    expect(within(card).getByText('✓ Resuelto')).toBeTruthy()
    await user.click(within(card).getByRole('button', { name: 'Reintentar paso 2' }))
    expect(await within(card).findByText('✓ A una persona')).toBeTruthy()
    expect(sendMessage).toHaveBeenCalledTimes(3)
    expect(sendMessage.mock.calls[2][0].data.key).toBe(sendMessage.mock.calls[1][0].data.key)
    expect(sendMessage.mock.calls[2][0].data.message).toBe('Me clonaron la tarjeta')
  })

  it('a step the API has whose message a reload dropped from the conversation is retried with its own key, not sent as new', async () => {
    const user = userEvent.setup()
    history.initial = { ok: false, failure: 'unavailable' }
    getHistory.mockResolvedValue({ ok: true, cases: [], turns: [{ role: 'user', text: '¿Cuál es mi saldo?', at: 1 }, { role: 'assistant', reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.'), at: 2 }] })
    sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: false, failure: 'already_processed' })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await user.click(await within(card).findByRole('button', { name: 'Reintentar paso 1' }))
    await within(card).findByText(/ya llegó/)
    await user.click(document.querySelector('.chat__history button') as HTMLElement)
    await waitFor(() => expect(document.querySelector('.chat__history')).toBeNull())

    const again = await within(card).findByRole('button', { name: 'Reintentar paso 1' })
    expect(within(card).queryByRole('button', { name: 'Enviar paso 1' })).toBeNull()
    await user.click(again)
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
    expect(sendMessage).toHaveBeenCalledTimes(3)
    expect(sendMessage.mock.calls[2][0].data.key).toBe(sendMessage.mock.calls[0][0].data.key)
  })

  it('restarting the scenario starts its steps from zero, in the new session', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      .mockReturnValueOnce(new Promise(() => {}))
    await draw()
    const card = await load(user, 'Dos turnos')
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()

    await user.click(within(card).getByRole('button', { name: 'Reiniciar' }))

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(2))
    expect(sendMessage.mock.calls[1][0].data.message).toBe('¿Cuál es mi saldo?')
    expect(sendMessage.mock.calls[1][0].data.key).not.toBe(sendMessage.mock.calls[0][0].data.key)
    expect(within(card).queryByText('✓ Resuelto')).toBeNull()
    expect((within(card).getByRole('button', { name: 'Enviar paso 1' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('a step the API already has is not sent again from the card: the button is off and the card points at the chat', async () => {
    const user = userEvent.setup()
    sendMessage.mockResolvedValueOnce({ ok: false, failure: 'already_processed' })
    await draw()
    const card = await load(user, 'Dos turnos')
    expect((await within(card).findByText(/ya llegó/)).textContent).toContain('recarga')
    expect((within(card).getByRole('button', { name: 'Enviar paso 1' }) as HTMLButtonElement).disabled).toBe(true)
    expect(sendMessage).toHaveBeenCalledOnce()
  })

  it('the step button goes off with the composer when the session runs out on the clock, before the API says so', async () => {
    const user = userEvent.setup()
    sendMessage.mockResolvedValue({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    // The session's countdown ticks every five seconds: its ticks are held to be run by hand, and only the date is faked, so the
    // queries and the user go on with real timers.
    const ticks: (() => void)[] = []
    const real = globalThis.setInterval
    vi.spyOn(globalThis, 'setInterval').mockImplementation(((fn: () => void, ms?: number) => {
      if (ms === 5_000) { ticks.push(fn); return 0 as unknown as ReturnType<typeof setInterval> }
      return real(fn, ms)
    }) as typeof setInterval)
    await draw()
    const card = await load(user, 'Dos turnos')
    const step = await within(card).findByRole('button', { name: 'Enviar paso 2' })
    expect((step as HTMLButtonElement).disabled).toBe(false)

    vi.useFakeTimers({ toFake: ['Date'] })
    try {
      vi.setSystemTime(Date.now() + 901_000)
      await act(async () => { ticks.forEach((tick) => tick()) })
    } finally {
      vi.useRealTimers()
    }

    await waitFor(() => expect(input().disabled).toBe(true))
    expect((within(card).getByRole('button', { name: 'Enviar paso 2' }) as HTMLButtonElement).disabled).toBe(true)
    await user.click(within(card).getByRole('button', { name: 'Enviar paso 2' }))
    expect(sendMessage).toHaveBeenCalledOnce()
  })

  it('the late reply of another message is not the answer of a step that failed', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: false, failure: 'busy' })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'El dólar está a 17 pesos.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await screen.findByRole('button', { name: 'Reintentar' })
    await user.type(input(), '¿A cuánto está el dólar?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Reintentar' })).toHaveLength(2))
    await user.click(screen.getAllByRole('button', { name: 'Reintentar' })[1])
    await screen.findByText('El dólar está a 17 pesos.')

    expect(sendMessage.mock.calls[1][0].data.key).toBe(sendMessage.mock.calls[2][0].data.key)
    expect(within(card).queryByText('✓ Resuelto')).toBeNull()
    expect(within(card).getByRole('status').textContent).toContain('no cuenta como paso')
    expect(within(card).getByRole('button', { name: 'Reintentar paso 1' })).toBeTruthy()
  })

  it('the step button is off while a message is on its way, and comes back for the next step when it is answered', async () => {
    const user = userEvent.setup()
    let answer: (value: unknown) => void = () => {}
    sendMessage.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(sendMessage).toHaveBeenCalledOnce())

    const first = within(card).getByRole('button', { name: 'Enviar paso 1' }) as HTMLButtonElement
    expect(first.disabled).toBe(true)
    await user.click(first)
    expect(sendMessage).toHaveBeenCalledOnce()
    await act(async () => { answer({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') }) })
    await waitFor(() => expect((within(card).getByRole('button', { name: 'Enviar paso 2' }) as HTMLButtonElement).disabled).toBe(false))
  })

  it('loading a scenario leaves no draft behind: the session it belonged to is gone', async () => {
    const user = userEvent.setup()
    await draw()
    await user.type(input(), 'algo a medias')
    await load(user, 'Primero')
    await waitFor(() => expect(sendMessage).toHaveBeenCalledOnce())
    expect(sendMessage.mock.calls[0][0].data.message).toBe('uno')
    expect(input().value).toBe('')
  })

  it('in Portuguese the step button speaks Portuguese and sends the step', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      .mockResolvedValueOnce({ ok: true, reply: reply('ESCALATE', 'Te paso con una persona.') })
    await draw('pt')
    const aside = await screen.findByRole('complementary', { name: 'Recursos de demonstração' })
    const card = within(aside).getByRole('article', { name: 'Dos turnos (PT)' })
    await user.click(within(card).getByRole('button', { name: 'Carregar' }))
    expect(await screen.findByText('¿Cuál es mi saldo?')).toBeTruthy()
    await user.click(await within(card).findByRole('button', { name: 'Enviar passo 2' }))
    expect(await screen.findByText('Te paso con una persona.')).toBeTruthy()
    expect(sendMessage.mock.calls[1][0].data.message).toBe('Me clonaron la tarjeta')
  })

  describe('on a narrow screen, where the panel is a drawer', () => {
    beforeEach(() => phone(true))

    it('choosing a scenario closes the drawer, gives the page back and puts the focus in the input while the message is on its way', async () => {
      const user = userEvent.setup()
      const { container } = await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const drawer = container.querySelector('#shell-demo') as HTMLElement
      expect(drawer.hasAttribute('inert')).toBe(false)
      expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(true)
      let answer: (value: unknown) => void = () => {}
      sendMessage.mockReturnValue(new Promise((resolve) => { answer = resolve }))

      await load(user, 'Dos turnos')

      expect(await screen.findByText('¿Cuál es mi saldo?')).toBeTruthy()
      await waitFor(() => expect(drawer.hasAttribute('inert')).toBe(true))
      expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(false)
      await waitFor(() => expect(document.activeElement).toBe(input()))
      // The chat shows the message and, when it comes, the reply.
      await act(async () => { answer({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') }) })
      expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
      await waitFor(() => expect(document.activeElement).toBe(input()))
    })

    it('the step button of a reopened drawer sends the step, closes the drawer over the chat and leaves the focus in the input', async () => {
      const user = userEvent.setup()
      sendMessage
        .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
        .mockResolvedValueOnce({ ok: true, reply: reply('ESCALATE', 'Te paso con una persona.') })
      const { container } = await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const card = await load(user, 'Dos turnos')
      await screen.findByText('Tu saldo es 10 USD.')
      await user.click(screen.getByRole('button', { name: 'Demo' }))
      const drawer = container.querySelector('#shell-demo') as HTMLElement
      expect(drawer.hasAttribute('inert')).toBe(false)

      await user.click(within(card).getByRole('button', { name: 'Enviar paso 2' }))

      expect(await screen.findByText('Te paso con una persona.')).toBeTruthy()
      expect(sendMessage.mock.calls[1][0].data.message).toBe('Me clonaron la tarjeta')
      await waitFor(() => expect(drawer.hasAttribute('inert')).toBe(true))
      await waitFor(() => expect(document.activeElement).toBe(input()))
    })
    it('reopening the drawer with a scenario in course puts the focus on its card, not on the top of the panel', async () => {
      const user = userEvent.setup()
      const { container } = await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const card = await load(user, 'Dos turnos')
      await waitFor(() => expect(document.activeElement).toBe(input()))
      const drawer = container.querySelector('#shell-demo') as HTMLElement
      expect(drawer.hasAttribute('inert')).toBe(true)

      await user.click(screen.getByRole('button', { name: 'Demo' }))

      expect(drawer.hasAttribute('inert')).toBe(false)
      expect(document.activeElement).toBe(card)
      expect(within(card).getByRole('region', { name: 'Pasos del escenario' })).toBeTruthy()
      // The focus stays inside the drawer, and Escape gives the page back.
      for (let i = 0; i < 12; i++) {
        await user.tab()
        expect(drawer.contains(document.activeElement), `Tab #${i + 1}`).toBe(true)
      }
      await user.keyboard('{Escape}')
      expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(false)
    })

    async function reopenedOnCard() {
      const user = userEvent.setup()
      sendMessage.mockResolvedValue({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const card = await load(user, 'Dos turnos')
      await screen.findByText('Tu saldo es 10 USD.')
      await waitFor(() => expect(document.activeElement).toBe(input()))
      await user.click(screen.getByRole('button', { name: 'Demo' }))
      expect(document.activeElement).toBe(card)
      return { user, card }
    }

    it('Tab from the active card goes on to the next control after it, not back to the head of the panel', async () => {
      const { user, card } = await reopenedOnCard()
      await user.tab()
      expect(document.activeElement).toBe(within(card).getByRole('button', { name: 'Reiniciar' }))
    })

    it('Shift+Tab from the active card goes to the control before it', async () => {
      const { user, card } = await reopenedOnCard()
      await user.tab({ shift: true })
      const before = document.activeElement as HTMLElement
      expect(before.tagName).toBe('BUTTON')
      expect(card.contains(before)).toBe(false)
      expect(before).not.toBe(screen.getByRole('button', { name: 'Cerrar' }))
      expect(within(before.closest('article') as HTMLElement).getByRole('button', { name: 'Cargar' })).toBe(before)
    })

    it('reopened with no scenario in course it still opens on the first control', async () => {
      const user = userEvent.setup()
      await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      expect((document.activeElement as HTMLElement).getAttribute('aria-label') ?? document.activeElement?.textContent).toMatch(/Cerrar/)
    })
  })
})
