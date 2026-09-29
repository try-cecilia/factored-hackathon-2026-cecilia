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
import type { DemoScenario, Reply } from './types'

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
vi.mock('../server/chat.functions', () => ({ sendMessage, getHistory: vi.fn(), getCase: vi.fn() }))

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
    <ConversationProvider sessionRef={ref} initial={{ ok: true, cases: [], turns: [] }}>
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
  sendMessage.mockReset()
})
afterEach(() => vi.restoreAllMocks())

describe('a scenario of the demo panel writes its message in the chat input', () => {
  it('choosing a scenario far down the list leaves its first message in the input, focused, and draws nothing above the list', async () => {
    const user = userEvent.setup()
    await draw()
    const aside = await panel()
    const before = within(aside).getAllByRole('region').map((r) => r.getAttribute('aria-label'))
    expect(before[0]).toBe('Escenarios guiados')

    const card = await load(user, 'Dos turnos')

    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
    expect(document.activeElement).toBe(input())
    expect(input().selectionStart).toBe(input().value.length)
    // Its steps are in its own card, in its place; above the list there is still nothing but the scenarios.
    expect(within(card).getByRole('region', { name: 'Pasos del escenario' })).toBeTruthy()
    expect(within(aside).getAllByRole('region')[0].getAttribute('aria-label')).toBe('Escenarios guiados')
    expect(within(aside).getAllByRole('region', { name: 'Pasos del escenario' })).toHaveLength(1)
    // Nothing was sent by itself, and the steps have no "send" button of their own.
    expect(sendMessage).not.toHaveBeenCalled()
    expect(within(card).queryByRole('button', { name: 'Enviar este mensaje' })).toBeNull()
  })

  it('the person sends it from the composer, and the reply fills the step and leaves the next message in the input', async () => {
    const user = userEvent.setup()
    sendMessage.mockResolvedValue({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))

    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))

    expect(sendMessage).toHaveBeenCalledOnce()
    expect(sendMessage.mock.calls[0][0].data).toMatchObject({ message: '¿Cuál es mi saldo?', key: expect.any(String) })
    expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
    await waitFor(() => expect(input().value).toBe('Me clonaron la tarjeta'))
    expect(document.activeElement).toBe(input())
    expect(within(card).getByText('✓ Resuelto')).toBeTruthy()
  })

  it('the second step is judged against what was expected, with the message sent from the composer', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
      .mockResolvedValueOnce({ ok: true, reply: reply('CLARIFY', '¿Qué pasó exactamente?') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await waitFor(() => expect(input().value).toBe('Me clonaron la tarjeta'))
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))

    expect(await within(card).findByText('✗ Salió Pregunta')).toBeTruthy()
    // The scenario is over: nothing more is written into the input.
    expect(input().value).toBe('')
    expect(within(card).queryByRole('button', { name: 'Volver a escribir el mensaje' })).toBeNull()
  })

  it('a message the person is writing is not lost when the next step arrives; asking for the step again does replace it', async () => {
    const user = userEvent.setup()
    let answer: (value: unknown) => void = () => {}
    sendMessage.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))

    await user.type(input(), 'mi propio borrador')
    await act(async () => { answer({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') }) })
    expect(await screen.findByText('Tu saldo es 10 USD.')).toBeTruthy()
    expect(within(card).getByText('✓ Resuelto')).toBeTruthy()
    expect(input().value).toBe('mi propio borrador')

    await user.click(within(card).getByRole('button', { name: 'Volver a escribir el mensaje' }))
    expect(input().value).toBe('Me clonaron la tarjeta')
    expect(document.activeElement).toBe(input())
  })

  it('a reply to a message that is not the step is not the step: the card says so and the scenario stays where it was', async () => {
    const user = userEvent.setup()
    sendMessage.mockResolvedValue({ ok: true, reply: reply('AUTO_RESOLVE', 'El dólar está a 17 pesos.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))

    await user.clear(input())
    await user.type(input(), '¿A cuánto está el dólar?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))

    expect(await screen.findByText('El dólar está a 17 pesos.')).toBeTruthy()
    expect(within(card).getByRole('status', { name: '' }).textContent).toContain('no cuenta como paso')
    expect(within(card).queryByText(/^✓/)).toBeNull()
    // Still on the first step: asking for it again writes the first message, not the second.
    await user.click(within(card).getByRole('button', { name: 'Volver a escribir el mensaje' }))
    expect(input().value).toBe('¿Cuál es mi saldo?')

    // Back on the script, the step is answered and the note goes.
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    expect(await within(card).findByText('✓ Resuelto')).toBeTruthy()
    expect(within(card).queryByRole('status')).toBeNull()
    await waitFor(() => expect(input().value).toBe('Me clonaron la tarjeta'))
  })

  it('a step whose message failed and was retried after other messages is answered by the retry, not lost', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'El dólar está a 17 pesos.') })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await screen.findByRole('button', { name: 'Reintentar' })
    await user.type(input(), '¿A cuánto está el dólar?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await screen.findByText('El dólar está a 17 pesos.')
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByText('Tu saldo es 10 USD.')

    expect(sendMessage.mock.calls[0][0].data.key).toBe(sendMessage.mock.calls[2][0].data.key)
    expect(within(card).getByText('✓ Resuelto')).toBeTruthy()
    expect(within(card).queryByRole('status')).toBeNull()
    await waitFor(() => expect(input().value).toBe('Me clonaron la tarjeta'))
  })

  it('the late reply of another message is not the answer of a step that failed', async () => {
    const user = userEvent.setup()
    sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: false, failure: 'busy' })
      .mockResolvedValueOnce({ ok: true, reply: reply('AUTO_RESOLVE', 'El dólar está a 17 pesos.') })
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
    await user.clear(input())
    await user.type(input(), '¿A cuánto está el dólar?')
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await screen.findByRole('button', { name: 'Reintentar' })
    await user.click(within(card).getByRole('button', { name: 'Volver a escribir el mensaje' }))
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Reintentar' })).toHaveLength(2))
    await user.click(screen.getAllByRole('button', { name: 'Reintentar' })[0])
    await screen.findByText('El dólar está a 17 pesos.')

    expect(sendMessage.mock.calls[0][0].data.key).toBe(sendMessage.mock.calls[2][0].data.key)
    expect(within(card).queryByText('✓ Resuelto')).toBeNull()
    expect(within(card).getByRole('status').textContent).toContain('no cuenta como paso')
    expect(input().value).not.toBe('Me clonaron la tarjeta')
  })

  it('asking for the step again is off while a message is on its way, so the input cannot go back a step', async () => {
    const user = userEvent.setup()
    let answer: (value: unknown) => void = () => {}
    sendMessage.mockReturnValue(new Promise((resolve) => { answer = resolve }))
    await draw()
    const card = await load(user, 'Dos turnos')
    await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
    await user.click(screen.getByRole('button', { name: 'Enviar mensaje' }))

    const again = within(card).getByRole('button', { name: 'Volver a escribir el mensaje' }) as HTMLButtonElement
    expect(again.disabled).toBe(true)
    await act(async () => { answer({ ok: true, reply: reply('AUTO_RESOLVE', 'Tu saldo es 10 USD.') }) })
    await waitFor(() => expect(input().value).toBe('Me clonaron la tarjeta'))
    expect((within(card).getByRole('button', { name: 'Volver a escribir el mensaje' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('loading a scenario replaces a draft: the person chose it, and the session it belonged to is gone', async () => {
    const user = userEvent.setup()
    await draw()
    await user.type(input(), 'algo a medias')
    await load(user, 'Primero')
    await waitFor(() => expect(input().value).toBe('uno'))
  })

  it('in Portuguese the panel and the input speak Portuguese', async () => {
    const user = userEvent.setup()
    await draw('pt')
    const aside = await screen.findByRole('complementary', { name: 'Recursos de demonstração' })
    const card = within(aside).getByRole('article', { name: 'Dos turnos (PT)' })
    await user.click(within(card).getByRole('button', { name: 'Carregar' }))
    const field = screen.getByRole('textbox', { name: 'Escreva a sua mensagem para a Cecilia' }) as HTMLTextAreaElement
    await waitFor(() => expect(field.value).toBe('¿Cuál es mi saldo?'))
    expect(document.activeElement).toBe(field)
    expect(within(card).getByRole('button', { name: 'Escrever a mensagem de novo' })).toBeTruthy()
  })

  describe('on a narrow screen, where the panel is a drawer', () => {
    beforeEach(() => phone(true))

    it('choosing a scenario closes the drawer, gives the page back and puts the focus in the input', async () => {
      const user = userEvent.setup()
      const { container } = await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const drawer = container.querySelector('#shell-demo') as HTMLElement
      expect(drawer.hasAttribute('inert')).toBe(false)
      expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(true)

      await load(user, 'Dos turnos')

      await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
      expect(drawer.hasAttribute('inert')).toBe(true)
      expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(false)
      expect(document.activeElement).toBe(input())
    })
    it('reopening the drawer with a scenario in course puts the focus on its card, not on the top of the panel', async () => {
      const user = userEvent.setup()
      const { container } = await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const card = await load(user, 'Dos turnos')
      await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
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
      await draw()
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const card = await load(user, 'Dos turnos')
      await waitFor(() => expect(input().value).toBe('¿Cuál es mi saldo?'))
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
