import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DemoEntry } from '../../server/demo-entry'
import { renderWithI18n } from '../../test/render'
import { translator } from '../../i18n/translate'
import { dictionaries } from '../../test/render'
import { BankBridgeCard } from './BankBridgeCard'
import { EnterDemoButton } from './EnterDemo'
import { withKnownConflict } from './results'
import { DemoBar } from './DemoBar'
import { EnterDemoDialog } from './EnterDemoDialog'

const navigate = vi.hoisted(() => vi.fn(async () => {}))
const invalidate = vi.hoisted(() => vi.fn(async () => {}))
const logout = vi.hoisted(() => vi.fn())
const enterDemo = vi.hoisted(() => vi.fn())
// Where the visitor is, for the entry button's cancel: the entry link unless a test says otherwise.
const location = vi.hoisted(() => ({ current: { pathname: '/', search: { demo: 'entrar' } as Record<string, string> } }))
vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: { select: (state: { location: typeof location.current }) => unknown }) => select({ location: location.current }),
  Link: ({ to, params, children, ...rest }: { to: string; params?: Record<string, string>; children?: ReactNode }) => (
    <a href={params ? Object.entries(params).reduce((path, [key, value]) => path.replace(`$${key}`, value), to) : to} {...rest}>{children}</a>
  ),
  useNavigate: () => navigate,
  useRouter: () => ({ invalidate }),
}))
vi.mock('../../server/auth.functions', () => ({ logout }))
vi.mock('../../server/demo.functions', () => ({ enterDemo }))

const entries: DemoEntry[] = [
  { role: 'cuentas', customer_id: 'CLI-FIX0001', language: 'es' },
  { role: 'pendiente', customer_id: 'CLI-FIX0003', language: 'es' },
  { role: 'portugues', customer_id: 'CLI-FIX0005', language: 'pt' },
]

beforeEach(() => {
  location.current = { pathname: '/', search: { demo: 'entrar' } }
  navigate.mockClear()
  invalidate.mockClear()
  logout.mockReset().mockResolvedValue({ revoked: true })
  enterDemo.mockReset().mockResolvedValue({ ok: true, language: 'es' })
})
afterEach(() => vi.useRealTimers())

describe('DemoBar', () => {
  it('marks the side being seen and switches with one click to the other', () => {
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="cuentas" />)
    const bar = screen.getByRole('region', { name: 'Modo demo' })
    expect(within(bar).getByText('DEMO')).toBeTruthy()
    expect(within(bar).getByText('Estás viendo la app como un cliente de prueba')).toBeTruthy()
    const roles = within(bar).getByRole('navigation', { name: 'Ver como' })
    expect(within(roles).getByRole('link', { name: 'Cliente' }).getAttribute('aria-current')).toBe('page')
    const bank = within(roles).getByRole('link', { name: 'Banco' })
    expect(bank.getAttribute('aria-current')).toBeNull()
    expect(bank.getAttribute('href')).toBe('/demo/banco')
    expect(screen.queryByRole('button', { name: 'Entrar otra vez' })).toBeNull()
  })

  it('on the bank side it says only the visitor\'s cases appear, and marks "Banco"', () => {
    renderWithI18n(<DemoBar view="bank" sessionRef="s1" expiresIn={900} role="cuentas" />)
    expect(screen.getByText('Estás viendo la consola del banco. Solo aparecen los casos que abriste.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Banco' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Cliente' }).getAttribute('href')).toBe('/chat')
  })

  it('"Salir de la demo" signs the customer out and goes to the home page', async () => {
    renderWithI18n(<DemoBar view="bank" sessionRef="s1" expiresIn={900} role="cuentas" />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Salir de la demo' }))
    expect(logout).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/' }))
  })

  it('in the last three minutes it counts down and offers to enter again as the same customer', async () => {
    renderWithI18n(<DemoBar view="bank" sessionRef="s1" expiresIn={170} role="pendiente" />)
    expect(screen.getByText('La demo termina en 2:50')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('Quedan menos de 3 minutos de demo')
    expect(screen.queryByText(/Solo aparecen los casos/)).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Entrar otra vez' }))
    expect(enterDemo).toHaveBeenCalledWith({ data: { role: 'pendiente' } })
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/demo/banco' }))
    expect(invalidate).toHaveBeenCalled()
  })

  it('the countdown moves with the clock and ends in "La demo terminó"', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={185} role="cuentas" />)
    expect(screen.queryByRole('button', { name: 'Entrar otra vez' })).toBeNull()
    await act(async () => { vi.advanceTimersByTime(10_000) })
    expect(screen.getByText('La demo termina en 2:55')).toBeTruthy()
    await act(async () => { vi.advanceTimersByTime(180_000) })
    expect(screen.getByRole('status').textContent).toBe('La demo terminó')
    expect(screen.getByRole('button', { name: 'Entrar otra vez' })).toBeTruthy()
  })

  it('a failed re-entry is said, and a session of no known customer goes to the entry dialog', async () => {
    enterDemo.mockResolvedValue({ ok: false, reason: 'failed' })
    const { unmount } = renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={0} role="cuentas" />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Entrar otra vez' }))
    expect(await screen.findByText('No se pudo entrar otra vez.')).toBeTruthy()
    expect(navigate).not.toHaveBeenCalled()
    unmount()
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={0} role={null} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Entrar otra vez' }))
    expect(navigate).toHaveBeenCalledWith({ href: '/?demo=entrar' })
    expect(enterDemo).toHaveBeenCalledTimes(1)
  })

  it('while a message is on its way, "Banco" waits: no link, and the reason is said', async () => {
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="cuentas" holdBank />)
    const bank = screen.getByRole('link', { name: 'Banco' })
    expect(bank.getAttribute('aria-disabled')).toBe('true')
    expect(bank.getAttribute('href')).toBeNull()
    expect(bank.getAttribute('title')).toBe('Esperando la respuesta de Cecilia')
    await userEvent.setup().click(bank)
    expect(navigate).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'Cliente' }).getAttribute('href')).toBe('/chat')
  })

  it('speaks Portuguese', () => {
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="portugues" />, 'pt')
    expect(screen.getByRole('button', { name: 'Sair da demo' })).toBeTruthy()
    expect(screen.getByText('Você está vendo o app como um cliente de teste')).toBeTruthy()
  })
})

describe('EnterDemoDialog', () => {
  const showModal = vi.fn(function (this: HTMLDialogElement) { this.setAttribute('open', '') })
  beforeEach(() => {
    showModal.mockClear()
    HTMLDialogElement.prototype.showModal = showModal
  })
  afterEach(() => {
    delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal
  })

  it('opens as a modal dialog with the test customers, the first one chosen', () => {
    renderWithI18n(<EnterDemoDialog open entries={entries} onClose={() => {}} />)
    expect(showModal).toHaveBeenCalledTimes(1)
    const dialog = screen.getByRole('dialog', { name: 'Probar Cecilia como cliente' })
    const options = within(dialog).getAllByRole('radio')
    expect(options).toHaveLength(3)
    expect((within(dialog).getByRole('radio', { name: /Varias cuentas y una tarjeta/ }) as HTMLInputElement).checked).toBe(true)
    expect(within(dialog).getByText('Son cuentas inventadas que comparten todos los visitantes: no escribir datos reales.')).toBeTruthy()
  })

  it('enters as the chosen customer with one click, with no PIN, and lands in the chat', async () => {
    const onClose = vi.fn()
    renderWithI18n(<EnterDemoDialog open entries={entries} onClose={onClose} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('radio', { name: /Una transferencia pendiente/ }))
    await user.click(screen.getByRole('button', { name: 'Entrar a la demo' }))
    expect(enterDemo).toHaveBeenCalledWith({ data: { role: 'pendiente' } })
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/chat' }))
    expect(invalidate).toHaveBeenCalled()
    // Entering is not cancelling: the close handler (which leaves the entry link) is not called on the way to the chat.
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('the keyboard picks a customer and enters: Space on a radio, Enter on the form', async () => {
    renderWithI18n(<EnterDemoDialog open entries={entries} onClose={() => {}} />)
    const user = userEvent.setup()
    screen.getByRole('radio', { name: /Cliente que habla portugués/ }).focus()
    await user.keyboard(' ')
    expect((screen.getByRole('radio', { name: /Cliente que habla portugués/ }) as HTMLInputElement).checked).toBe(true)
    await user.keyboard('{Enter}')
    expect(enterDemo).toHaveBeenCalledWith({ data: { role: 'portugues' } })
  })

  it('while entering the button says so and the options are held; a refusal is said and nothing navigates', async () => {
    let answer!: (value: unknown) => void
    enterDemo.mockReturnValue(new Promise((done) => (answer = done)))
    renderWithI18n(<EnterDemoDialog open entries={entries} onClose={() => {}} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Entrar a la demo' }))
    expect(screen.getByRole('button', { name: /Entrando/ })).toBeTruthy()
    expect(screen.getByRole('radio', { name: /Varias cuentas/ }).matches(':disabled')).toBe(true)
    await act(async () => answer({ ok: false, reason: 'limited', retryAfter: 42 }))
    expect(screen.getByRole('alert').textContent).toBe('Demasiados intentos seguidos. Intentar de nuevo en 42 s.')
    expect(navigate).not.toHaveBeenCalled()
  })

  it('a demo that is off (an HTTP 404), or an error on the way, is said with a fixed text', async () => {
    enterDemo.mockRejectedValueOnce(new Error('Not Found')).mockRejectedValueOnce(new Error('network'))
    renderWithI18n(<EnterDemoDialog open entries={entries} onClose={() => {}} />)
    const user = userEvent.setup()
    for (let i = 0; i < 2; i++) {
      await user.click(screen.getByRole('button', { name: 'Entrar a la demo' }))
      await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('No se pudo entrar a la demo. Intentar de nuevo.'))
    }
    expect(navigate).not.toHaveBeenCalled()
  })

  it('the close button closes it', async () => {
    const onClose = vi.fn()
    renderWithI18n(<EnterDemoDialog open entries={entries} onClose={onClose} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('in Portuguese', () => {
    renderWithI18n(<EnterDemoDialog open entries={entries} onClose={() => {}} />, 'pt')
    expect(screen.getByRole('dialog', { name: 'Experimentar a Cecilia como cliente' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Entrar na demo' })).toBeTruthy()
  })
})

describe('EnterDemoButton, reached through the entry link (/?demo=entrar)', () => {
  const showModal = vi.fn(function (this: HTMLDialogElement) { this.setAttribute('open', '') })
  beforeEach(() => void (HTMLDialogElement.prototype.showModal = showModal))
  afterEach(() => void delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal)

  it('entering lands in the chat and nothing sends the visitor back to the landing', async () => {
    renderWithI18n(<EnterDemoButton entries={entries} initiallyOpen />)
    await userEvent.setup().click(screen.getByRole('dialog').querySelector('button[type="submit"]') as HTMLButtonElement)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/chat' }))
    expect(navigate).toHaveBeenCalledTimes(1)
    expect(navigate).not.toHaveBeenCalledWith(expect.objectContaining({ to: '/' }))
  })

  it('cancelling on the entry link leaves the link out of the address', async () => {
    renderWithI18n(<EnterDemoButton entries={entries} initiallyOpen />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(navigate).toHaveBeenCalledWith({ to: '/', search: {}, replace: true })
  })

  it('a close that comes when the visitor is no longer on the entry link does not move them', async () => {
    location.current = { pathname: '/chat', search: {} }
    renderWithI18n(<EnterDemoButton entries={entries} initiallyOpen />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(navigate).not.toHaveBeenCalled()
  })
})

describe('the known conflict of the demo', () => {
  it('"another person took this case" is said in the page\'s language; a version conflict goes on as it came', () => {
    const taken = { ok: false as const, status: 409, message: 'another person took this case' }
    expect(withKnownConflict(translator(dictionaries.es), taken).message).toBe('Otra persona del banco tomó este caso.')
    expect(withKnownConflict(translator(dictionaries.pt), taken).message).toBe('Outra pessoa do banco assumiu este caso.')
    const stale = { ok: false as const, status: 409, message: 'stale version: expected 1, ticket is at 2' }
    expect(withKnownConflict(translator(dictionaries.es), stale)).toBe(stale)
    const ok = { ok: true as const }
    expect(withKnownConflict(translator(dictionaries.es), ok)).toBe(ok)
  })
})

describe('BankBridgeCard', () => {
  it('waits, with no way to the bank, while a message is on its way', () => {
    renderWithI18n(<BankBridgeCard ticketId="b99d8390-4d20" waiting />)
    const action = screen.getByRole('link', { name: /Verlo del lado del banco/ })
    expect(action.getAttribute('aria-disabled')).toBe('true')
    expect(action.getAttribute('href')).toBeNull()
  })

  it('takes the visitor to the same case on the bank\'s side', () => {
    renderWithI18n(<BankBridgeCard ticketId="b99d8390-4d20" />)
    const card = screen.getByRole('region', { name: 'Tu caso ya llegó al banco' })
    expect(within(card).getByRole('link', { name: /Verlo del lado del banco/ }).getAttribute('href')).toBe('/demo/banco/caso/b99d8390-4d20')
  })
})
