import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement, ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConversationProvider } from '../chat/ConversationProvider'
import type { HistoryResult } from '../chat/types'
import type { Session } from '../server/auth.functions'
import type { DemoKit } from '../server/demo.functions'
import { renderWithI18n } from '../test/render'
import { AppShell } from './AppShell'

const navigate = vi.hoisted(() => vi.fn())
const logout = vi.hoisted(() => vi.fn())
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...rest }: { to: string; children?: ReactNode }) => <a href={to} {...rest}>{children}</a>,
  useNavigate: () => navigate,
  useRouter: () => ({ invalidate: async () => {} }),
}))
vi.mock('../server/auth.functions', () => ({ logout }))
vi.mock('../server/locale.functions', () => ({ setLocale: vi.fn() }))
vi.mock('../server/demo.functions', () => ({ applyDemoFault: vi.fn(), getDemoTickets: async () => [], getDemoTraces: async () => [], startScenario: vi.fn() }))
vi.mock('../server/chat.functions', () => ({
  sendMessage: vi.fn(),
  getHistory: vi.fn(),
  getCase: async () => ({ ok: true, case: { ticket_id: 'T', status: 'claimed', message: null } }),
}))

const session: Session = { customer_id: 'CLI-FIX0001', session_ref: 's1', segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }
const ticket = '55d09c14-2235-4c3c-8967-ccac61db9c50'
const withCase: HistoryResult = {
  ok: true,
  cases: [],
  turns: [
    { role: 'user', text: 'Me clonaron la tarjeta', at: 1 },
    { role: 'assistant', at: 2, reply: { trace_id: 'abc12345', disposition: 'ESCALATE', response_text: 'Voy a transferir tu caso.', language: 'es', category: 'theft', ticket_id: ticket, latency_ms: 0 } },
  ],
}
const scenarios = [
  { id: 'a', path: 'normal', customer_id: 'CLI-FIX0001', language: 'es', fault: null, turns: ['hola'], expect: [null], title: { en: 'Balance', es: 'Consulta de saldo' }, look_for: { en: 'x', es: 'Se responde con datos.' } },
]

function phone(matches: boolean, narrow = matches) {
  window.matchMedia = ((query: string) => ({
    matches: (matches && query.includes('759px')) || (narrow && query.includes('1179px')), media: query, addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false, onchange: null,
  })) as unknown as typeof window.matchMedia
}

type Props = { history?: HistoryResult; scenarios?: typeof scenarios | null; kit?: Promise<DemoKit>; locale?: 'es' | 'pt' }

function shell(props: Props = {}): ReactElement {
  const kit = props.kit ?? Promise.resolve<DemoKit>(props.scenarios ? { enabled: true, scenarios: props.scenarios } : { enabled: false })
  return (
    <ConversationProvider sessionRef="s1" initial={props.history ?? { ok: true, cases: [], turns: [] }}>
      <AppShell session={session} kit={kit}><p>La página</p></AppShell>
    </ConversationProvider>
  )
}
// The demo's button and panel suspend on the kit: the first render is awaited inside act so they settle like in the browser.
async function draw(props: Props = {}) {
  let drawn: ReturnType<typeof renderWithI18n> | undefined
  await act(async () => { drawn = renderWithI18n(shell(props), props.locale ?? 'es') })
  return drawn as ReturnType<typeof renderWithI18n>
}

beforeEach(() => {
  phone(false)
  navigate.mockReset()
  logout.mockReset()
})
afterEach(() => vi.restoreAllMocks())

describe('AppShell', () => {
  it('the wide sidebar lists the chat and the cases of the conversation with where each stands', async () => {
    await draw({ history: withCase })
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    expect(within(nav).getByRole('link', { name: 'Chat' }).getAttribute('aria-current')).toBe('page')
    const row = await within(nav).findByRole('button', { name: /Robo o clonación de tarjeta/ })
    expect(await within(row).findByText(/En revisión · #55d09c14/)).toBeTruthy()
    expect(screen.getByText('1 abierto')).toBeTruthy()
  })

  it('with no cases it says so instead of leaving the section empty', async () => {
    await draw()
    expect(screen.getByText('Sin casos por ahora')).toBeTruthy()
  })

  it('collapses to a rail whose rows keep their names, and expands again', async () => {
    const user = userEvent.setup()
    await draw({ history: withCase })
    await user.click(screen.getByRole('button', { name: 'Contraer la barra lateral' }))
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    expect(within(nav).getByRole('link', { name: 'Chat' })).toBeTruthy()
    expect(within(nav).getByRole('button', { name: /Casos/ })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Expandir la barra lateral' }))
    expect(screen.queryByRole('button', { name: 'Expandir la barra lateral' })).toBeNull()
  })

  it('the language switcher is in the bar, in both languages', async () => {
    await draw()
    const group = screen.getByRole('group', { name: 'Idioma' })
    expect(within(group).getByRole('button', { name: 'Español' }).getAttribute('aria-pressed')).toBe('true')
    expect(within(group).getByRole('button', { name: 'Português' })).toBeTruthy()
  })

  it('in Portuguese the shell speaks Portuguese', async () => {
    await draw({ locale: 'pt', history: withCase })
    expect(screen.getByRole('navigation', { name: 'Principal' })).toBeTruthy()
    expect(screen.getByText('Casos')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Recolher a barra lateral' })).toBeTruthy()
    expect(screen.getByText('Sair')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Chat' })).toBeTruthy()
  })

  it('signing out closes the session and goes to the sign-in page', async () => {
    logout.mockResolvedValue(undefined)
    await draw()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Salir' }))
    expect(logout).toHaveBeenCalledOnce()
    expect(navigate).toHaveBeenCalledWith({ to: '/login' })
  })

  it('a sign-out that fails is told, not swallowed', async () => {
    logout.mockRejectedValue(new Error('down'))
    await draw()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Salir' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText('No se pudo cerrar la sesión.')).toBeTruthy()
  })

  it('the demo panel exists only when the sandbox does, and is marked as Demo', async () => {
    await draw({ scenarios })
    const panel = await screen.findByRole('complementary', { name: 'Ayudas de demostración' })
    expect(within(panel).getByText('Demo')).toBeTruthy()
    expect(within(panel).getByText('Consulta de saldo')).toBeTruthy()
  })

  it('without the sandbox there is no demo panel and no Demo button', async () => {
    const kit = Promise.resolve<DemoKit>({ enabled: false })
    await draw({ kit })
    expect(screen.queryByRole('complementary', { name: 'Ayudas de demostración' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Demo' })).toBeNull()
  })

  it('the chat does not wait for the demo kit: the page is there while it is pending, and the demo comes when it arrives', async () => {
    let arrive: (kit: DemoKit) => void = () => {}
    await draw({ history: withCase, kit: new Promise<DemoKit>((resolve) => { arrive = resolve }) })
    expect(screen.getByText('La página')).toBeTruthy()
    expect(screen.getByText('Salir')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Demo' })).toBeNull()
    arrive({ enabled: true, scenarios })
    expect(await screen.findByRole('button', { name: 'Demo' })).toBeTruthy()
    expect(await screen.findByRole('complementary', { name: 'Ayudas de demostración' })).toBeTruthy()
    expect(screen.getByText('La página')).toBeTruthy()
  })

  describe('modal panels keep the keyboard inside', () => {
    const inside = (root: HTMLElement | null) => root !== null && root.contains(document.activeElement)

    it('the phone drawer: Tab and Shift+Tab wrap inside it, and the page behind is inert while it is open', async () => {
      phone(true)
      const user = userEvent.setup()
      const { container } = await draw({ history: withCase, scenarios })
      const side = container.querySelector('#shell-side') as HTMLElement
      const main = container.querySelector('.shell__main') as HTMLElement
      expect(main.hasAttribute('inert')).toBe(false)
      await user.click(screen.getByRole('button', { name: 'Abrir el menú' }))
      expect(main.hasAttribute('inert')).toBe(true)
      for (let i = 0; i < 12; i++) {
        await user.tab()
        expect(inside(side), `Tab #${i + 1}: focus on ${document.activeElement?.tagName}`).toBe(true)
      }
      for (let i = 0; i < 12; i++) {
        await user.tab({ shift: true })
        expect(inside(side), `Shift+Tab #${i + 1}`).toBe(true)
      }
      await user.keyboard('{Escape}')
      expect(main.hasAttribute('inert')).toBe(false)
    })

    it('the demo panel on a narrow screen: same containment, and neither the sidebar nor the page can be reached', async () => {
      phone(false, true)
      const user = userEvent.setup()
      const { container } = await draw({ scenarios })
      await user.click(await screen.findByRole('button', { name: 'Demo' }))
      const demo = container.querySelector('#shell-demo') as HTMLElement
      await screen.findByRole('complementary', { name: 'Ayudas de demostración' })
      expect(demo.hasAttribute('inert')).toBe(false)
      expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(true)
      expect((container.querySelector('#shell-side') as HTMLElement).hasAttribute('inert')).toBe(true)
      for (let i = 0; i < 40; i++) {
        await user.tab()
        expect(inside(demo), `Tab #${i + 1}`).toBe(true)
      }
      await user.tab({ shift: true })
      expect(inside(demo)).toBe(true)
    })

    it('with the panel closed nothing is inert', async () => {
      phone(true)
      const { container } = await draw({ scenarios })
      expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(false)
    })
  })

  describe('on a phone', () => {
    beforeEach(() => phone(true))

    it('the sidebar is a drawer: out of reach until the menu button opens it, and Escape closes it and gives the focus back', async () => {
      const user = userEvent.setup()
      const { container } = await draw({ history: withCase })
      const side = container.querySelector('#shell-side') as HTMLElement
      expect(side.hasAttribute('inert')).toBe(true)
      const menu = screen.getByRole('button', { name: 'Abrir el menú' })
      expect(menu.getAttribute('aria-expanded')).toBe('false')
      await user.click(menu)
      expect(side.hasAttribute('inert')).toBe(false)
      expect(side.getAttribute('role')).toBe('dialog')
      expect(side.getAttribute('aria-modal')).toBe('true')
      await user.keyboard('{Escape}')
      expect(side.hasAttribute('inert')).toBe(true)
      expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Abrir el menú' }))
    })

    it('choosing a case closes the drawer', async () => {
      const user = userEvent.setup()
      const { container } = await draw({ history: withCase })
      await user.click(screen.getByRole('button', { name: 'Abrir el menú' }))
      await user.click(await screen.findByRole('button', { name: /Robo o clonación de tarjeta/ }))
      expect((container.querySelector('#shell-side') as HTMLElement).hasAttribute('inert')).toBe(true)
    })

    it('the scrim closes it too', async () => {
      const user = userEvent.setup()
      const { container } = await draw()
      await user.click(screen.getByRole('button', { name: 'Abrir el menú' }))
      await user.click(container.querySelector('.shell__scrim') as HTMLElement)
      expect((container.querySelector('#shell-side') as HTMLElement).hasAttribute('inert')).toBe(true)
    })
  })
})
