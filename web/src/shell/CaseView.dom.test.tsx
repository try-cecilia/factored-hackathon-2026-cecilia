import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatLog } from '../chat/ChatLog'
import { ConversationProvider, useConversation } from '../chat/ConversationProvider'
import type { CaseResult, HistoryResult } from '../chat/types'
import type { Session } from '../server/auth.functions'
import type { DemoKit } from '../server/demo.functions'
import { I18nProvider } from '../i18n/context'
import { dictionaries } from '../test/render'
import { AppShell } from './AppShell'
import { useShell } from './ShellContext'

const server = vi.hoisted(() => ({ getCase: vi.fn() }))
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...rest }: { to: string; children?: ReactNode }) => <a href={to} {...rest}>{children}</a>,
  useNavigate: () => vi.fn(),
  useRouter: () => ({ invalidate: async () => {} }),
}))
vi.mock('../server/auth.functions', () => ({ logout: vi.fn() }))
vi.mock('../server/locale.functions', () => ({ setLocale: vi.fn() }))
vi.mock('../server/chat.functions', () => ({ sendMessage: vi.fn(), getHistory: vi.fn(), getCase: server.getCase }))

const session: Session = { customer_id: 'CLI-FIX0001', session_ref: 's1', segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }
const ticket = '55d09c14-2235-4c3c-8967-ccac61db9c50'
const history: HistoryResult = {
  ok: true,
  cases: [],
  turns: [
    { role: 'user', text: 'Me clonaron la tarjeta', at: Date.UTC(2026, 8, 29, 13, 5) },
    { role: 'assistant', at: Date.UTC(2026, 8, 29, 13, 6), reply: { trace_id: 'abc12345', disposition: 'ESCALATE', response_text: 'Voy a transferir tu caso.', language: 'es', category: 'theft', ticket_id: ticket, latency_ms: 0 } },
  ],
}
const claimed: CaseResult = { ok: true, case: { ticket_id: ticket, status: 'claimed', message: 'Novedad de tu caso: un agente ya lo tomó y lo está revisando.' } }

// The page as ChatView wires it: the log's "Ver caso" goes to the shell.
function Page() {
  const { entries, cases } = useConversation()
  const { showCase } = useShell()
  return <ChatLog entries={entries} cases={cases} sending={false} live ended={false} onSend={() => {}} onRetry={() => {}} onReload={() => {}} onViewCase={showCase} onSignIn={() => {}} />
}

const kit = Promise.resolve<DemoKit>({ enabled: false })

/** The chat page of one session: another `ref` is what a Demo scenario leaves after signing in as another customer. */
function tree(locale: 'es' | 'pt', ref = 's1', initial: HistoryResult = history) {
  return (
    <I18nProvider locale={locale} messages={dictionaries[locale]}>
      <ConversationProvider sessionRef={ref} initial={initial}>
        <AppShell session={{ ...session, session_ref: ref }} kit={kit}><Page /></AppShell>
      </ConversationProvider>
    </I18nProvider>
  )
}

async function draw(locale: 'es' | 'pt' = 'es') {
  let drawn: ReturnType<typeof render> | undefined
  await act(async () => { drawn = render(tree(locale)) })
  return drawn as ReturnType<typeof render>
}

beforeEach(() => {
  server.getCase.mockReset()
  server.getCase.mockResolvedValue(claimed)
  window.matchMedia = ((query: string) => ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia
})

describe('the case view', () => {
  it('"Ver caso" opens it as a modal dialog: reason, status, what is happening, what comes next, the news and the number', async () => {
    const user = userEvent.setup()
    const { container } = await draw()
    await user.click(screen.getByRole('button', { name: /^Ver caso 55d09c14/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Robo o clonación de tarjeta' })
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(within(dialog).getByText('En revisión')).toBeTruthy()
    expect(within(dialog).getByText('Una persona del equipo tomó tu caso y lo está revisando.')).toBeTruthy()
    expect(within(dialog).getByText('Novedad de tu caso: un agente ya lo tomó y lo está revisando.')).toBeTruthy()
    expect(within(dialog).getByText(/Cecilia te la contará en tu próximo mensaje/)).toBeTruthy()
    expect(within(dialog).getByText(ticket)).toBeTruthy()
    // Modal: the page and the sidebar behind are inert, and the focus is inside, on its first control.
    expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(true)
    expect((container.querySelector('#shell-side') as HTMLElement).hasAttribute('inert')).toBe(true)
    expect(dialog.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: 'Cerrar el caso' }))
  })

  it('the case\'s row in the sidebar opens it too', async () => {
    const user = userEvent.setup()
    await draw()
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    await user.click(await within(nav).findByRole('button', { name: /Robo o clonación de tarjeta/ }))
    expect(await screen.findByRole('dialog', { name: 'Robo o clonación de tarjeta' })).toBeTruthy()
  })

  it('Escape closes it and gives the focus back to the button that opened it', async () => {
    const user = userEvent.setup()
    const { container } = await draw()
    const opener = screen.getByRole('button', { name: /^Ver caso 55d09c14/ })
    await user.click(opener)
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect((container.querySelector('#shell-case') as HTMLElement).hasAttribute('inert')).toBe(true)
    expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(false)
    expect(document.activeElement).toBe(opener)
  })

  it('Tab stays inside it', async () => {
    const user = userEvent.setup()
    await draw()
    await user.click(screen.getByRole('button', { name: /^Ver caso 55d09c14/ }))
    const dialog = await screen.findByRole('dialog')
    for (let i = 0; i < 8; i++) {
      await user.tab()
      expect(dialog.contains(document.activeElement), `Tab #${i + 1}`).toBe(true)
    }
  })

  it('"Actualizar el estado" asks the API again and says when', async () => {
    const user = userEvent.setup()
    await draw()
    await user.click(screen.getByRole('button', { name: /^Ver caso 55d09c14/ }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('En revisión')
    const asked = server.getCase.mock.calls.length
    server.getCase.mockResolvedValue({ ok: true, case: { ticket_id: ticket, status: 'approved', message: 'Novedad de tu caso: un agente aprobó el rastreo y abrió el pedido T-1. Operaciones responde en hasta 5 días hábiles.' } })
    await user.click(within(dialog).getByRole('button', { name: 'Actualizar el estado' }))
    expect(server.getCase.mock.calls.length).toBe(asked + 1)
    expect(await within(dialog).findByText('Aprobado')).toBeTruthy()
    expect(within(dialog).getByText(/Estado consultado a las/)).toBeTruthy()
  })

  it('when the status cannot be read it says so, and trying again can bring it', async () => {
    server.getCase.mockResolvedValue({ ok: false, failure: 'unavailable' })
    const user = userEvent.setup()
    await draw()
    await user.click(screen.getByRole('button', { name: /^Ver caso 55d09c14/ }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('No se pudo consultar el caso')).toBeTruthy()
    server.getCase.mockResolvedValue(claimed)
    await user.click(within(dialog).getByRole('button', { name: 'Intentar de nuevo' }))
    expect(await within(dialog).findByText('En revisión')).toBeTruthy()
  })

  it('a case the API does not find is said to be not found, not left loading', async () => {
    server.getCase.mockResolvedValue({ ok: false, failure: 'not_found' })
    const user = userEvent.setup()
    await draw()
    await user.click(screen.getByRole('button', { name: /^Ver caso 55d09c14/ }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('No se encontró este caso')).toBeTruthy()
    expect(within(dialog).queryByRole('button', { name: 'Actualizar el estado' })).toBeNull()
  })

  it('in Portuguese it speaks Portuguese', async () => {
    const user = userEvent.setup()
    await draw('pt')
    await user.click(screen.getByRole('button', { name: /^Ver caso 55d09c14/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Roubo ou clonagem de cartão' })
    expect(await within(dialog).findByText('O que está acontecendo')).toBeTruthy()
    expect(within(dialog).getByRole('button', { name: 'Atualizar o status' })).toBeTruthy()
    expect(within(dialog).getByRole('button', { name: 'Fechar o caso' })).toBeTruthy()
  })

  it('on a phone, opened from the drawer\'s row, the drawer closes and Escape gives the focus to the menu button', async () => {
    window.matchMedia = ((query: string) => ({ matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia
    const user = userEvent.setup()
    const { container } = await draw()
    await user.click(screen.getByRole('button', { name: 'Abrir el menú' }))
    const side = container.querySelector('#shell-side') as HTMLElement
    await user.click(await within(side).findByRole('button', { name: /Robo o clonación de tarjeta/ }))
    expect(await screen.findByRole('dialog', { name: 'Robo o clonación de tarjeta' })).toBeTruthy()
    expect(side.hasAttribute('inert')).toBe(true)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Abrir el menú' }))
  })

  it('a new session (another customer, from Demo) closes the previous session\'s case and keeps nothing of it', async () => {
    const user = userEvent.setup()
    const { container, rerender } = await draw()
    await user.click(screen.getByRole('button', { name: /^Ver caso 55d09c14/ }))
    await screen.findByRole('dialog')
    await act(async () => { rerender(tree('es', 's2', { ok: true, turns: [], cases: [] })) })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect((container.querySelector('#shell-case') as HTMLElement).textContent).toBe('')
    expect(screen.queryByText('Consultando el estado…')).toBeNull()
    expect((container.querySelector('.shell__main') as HTMLElement).hasAttribute('inert')).toBe(false)
  })
})
