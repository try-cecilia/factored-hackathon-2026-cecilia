import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DemoEntry } from '../../server/demo-entry'
import { renderWithI18n } from '../../test/render'
import { I18nProvider } from '../../i18n/context'
import { translator } from '../../i18n/translate'
import { dictionaries } from '../../test/render'
import { BankBridgeCard } from './BankBridgeCard'
import { withKnownConflict } from './results'
import { DemoBar } from './DemoBar'
import { DemoWelcome } from './DemoWelcome'
import { DemoExpired } from './DemoExpired'

const navigate = vi.hoisted(() => vi.fn(async () => {}))
const invalidate = vi.hoisted(() => vi.fn(async () => {}))
const logout = vi.hoisted(() => vi.fn())
const enterDemo = vi.hoisted(() => vi.fn())
vi.mock('@tanstack/react-router', () => ({
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
  window.localStorage.clear()
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

  it('a failed re-entry is said, and a session of no known customer enters again as the default one, straight away', async () => {
    enterDemo.mockResolvedValue({ ok: false, reason: 'failed' })
    const { unmount } = renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={0} role="cuentas" />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Entrar otra vez' }))
    expect(await screen.findByText('No se pudo entrar otra vez.')).toBeTruthy()
    expect(navigate).not.toHaveBeenCalled()
    unmount()
    enterDemo.mockResolvedValue({ ok: true, language: 'es' })
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={0} role={null} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Entrar otra vez' }))
    expect(enterDemo).toHaveBeenLastCalledWith({ data: { role: 'cuentas' } })
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/chat' }))
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

  it('a known end shows at once, and a new session after it counts afresh (the end of the old one is not carried over)', () => {
    const { rerender } = renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} ended role="cuentas" />)
    expect(screen.getByRole('status').textContent).toBe('La demo terminó')
    // The render where the new session arrives may still carry the old end: it must not stick to the new session.
    rerender(<I18nProvider locale="es" messages={dictionaries.es}><DemoBar view="customer" sessionRef="s2" expiresIn={900} ended role="cuentas" /></I18nProvider>)
    rerender(<I18nProvider locale="es" messages={dictionaries.es}><DemoBar view="customer" sessionRef="s2" expiresIn={900} role="cuentas" /></I18nProvider>)
    expect(screen.queryByRole('button', { name: 'Entrar otra vez' })).toBeNull()
    expect(screen.getByText('Estás viendo la app como un cliente de prueba')).toBeTruthy()
  })

  it('speaks Portuguese', () => {
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="portugues" />, 'pt')
    expect(screen.getByRole('button', { name: 'Sair da demo' })).toBeTruthy()
    expect(screen.getByText('Você está vendo o app como um cliente de teste')).toBeTruthy()
  })
})

describe('BankHint, on the customer\'s side of the bar', () => {
  it('says what Banco is the first time, and not again once closed', async () => {
    const { unmount } = renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="cuentas" />)
    const hint = await screen.findByRole('note')
    expect(hint.textContent).toContain('Banco: atiende tu caso como lo haría una persona del banco.')
    expect(screen.getByRole('link', { name: 'Banco' }).getAttribute('title')).toBe('Banco: atiende tu caso como lo haría una persona del banco.')
    await userEvent.setup().click(within(hint).getByRole('button', { name: 'Entendido' }))
    expect(screen.queryByRole('note')).toBeNull()
    unmount()
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="cuentas" />)
    await act(async () => {})
    expect(screen.queryByRole('note')).toBeNull()
  })

  it('opening Banco counts as having seen it: back on the customer\'s side it does not show', async () => {
    const { unmount } = renderWithI18n(<DemoBar view="bank" sessionRef="s1" expiresIn={900} role="cuentas" />)
    await act(async () => {})
    expect(screen.queryByRole('note')).toBeNull()
    unmount()
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="cuentas" />)
    await act(async () => {})
    expect(screen.queryByRole('note')).toBeNull()
  })

  it('in Portuguese', async () => {
    renderWithI18n(<DemoBar view="customer" sessionRef="s1" expiresIn={900} role="cuentas" />, 'pt')
    expect((await screen.findByRole('note')).textContent).toContain('Banco: atende o seu caso como faria uma pessoa do banco.')
  })
})

describe('DemoWelcome, the chat of the one-click demo before the first message', () => {
  it('says where the visitor is and offers three situations, each with the verb of what to do', () => {
    renderWithI18n(<DemoWelcome entries={entries} run={vi.fn()} />)
    const welcome = screen.getByRole('region', { name: 'Estás en la demo como un cliente de prueba.' })
    // What the bank's side shows, true of every card: the trace opens no case for a person, it shows under Traces.
    expect(within(welcome).getByText(/Puedes probar una de estas situaciones o escribir lo que quieras/).textContent).toContain(
      'verás lo que ve el banco: los casos que pasan a una persona y los rastreos que abriste.',
    )
    const cards = within(within(welcome).getByRole('list', { name: 'Situaciones para probar' })).getAllByRole('button')
    expect(cards.map((c) => c.querySelector('strong')?.textContent)).toEqual([
      'Consultar saldos y reclamar un cargo', 'Rastrear una transferencia que no llegó', 'Hablar en portugués',
    ])
  })

  it('a card starts its scenario through the demo panel (its customer and first message), and holds the others meanwhile', async () => {
    let done!: (ok: boolean) => void
    const run = vi.fn(() => new Promise<boolean>((resolve) => (done = resolve)))
    renderWithI18n(<DemoWelcome entries={entries} run={run} />)
    await userEvent.setup().click(screen.getByRole('button', { name: /Rastrear una transferencia que no llegó/ }))
    expect(run).toHaveBeenCalledWith('action_trace')
    expect(screen.getByRole('button', { name: /Rastrear una transferencia/ }).getAttribute('aria-busy')).toBe('true')
    expect(screen.getByText('Preparando la situación…')).toBeTruthy()
    for (const card of screen.getAllByRole('button')) expect((card as HTMLButtonElement).disabled).toBe(true)
    await act(async () => done(true))
    expect((screen.getByRole('button', { name: /Hablar en portugués/ }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('the other two scenarios, and a failure said with a fixed text', async () => {
    const run = vi.fn(async () => false)
    renderWithI18n(<DemoWelcome entries={entries} run={run} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Consultar saldos/ }))
    expect(run).toHaveBeenLastCalledWith('normal_balance')
    expect((await screen.findByRole('alert')).textContent).toBe('No se pudo preparar esa situación. Intentar de nuevo.')
    await user.click(screen.getByRole('button', { name: /Hablar en portugués/ }))
    expect(run).toHaveBeenLastCalledWith('normal_pt_arrears')
  })

  it('until the panel hands out its way to run a scenario, the cards wait', () => {
    renderWithI18n(<DemoWelcome entries={entries} run={null} />)
    for (const card of screen.getAllByRole('button')) expect((card as HTMLButtonElement).disabled).toBe(true)
  })

  it('in Portuguese', () => {
    renderWithI18n(<DemoWelcome entries={entries} run={vi.fn()} />, 'pt')
    expect(screen.getByRole('region', { name: 'Você está na demo como um cliente de teste.' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Rastrear uma transferência que não chegou/ })).toBeTruthy()
    expect(screen.getByText(/verá o que o banco vê: os casos que passam para uma pessoa e os rastreios que você abriu\./)).toBeTruthy()
  })
})

describe('DemoExpired, the bank\'s side after the session', () => {
  it('enters again straight away as the same customer, on the bank\'s side', async () => {
    renderWithI18n(<DemoExpired role="pendiente" />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Entrar otra vez' }))
    expect(enterDemo).toHaveBeenCalledWith({ data: { role: 'pendiente' } })
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/demo/banco' }))
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
