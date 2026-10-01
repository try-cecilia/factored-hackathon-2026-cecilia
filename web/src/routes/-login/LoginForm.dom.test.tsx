import { createMemoryHistory, createRootRoute, createRoute, createRouter, redirect, RouterProvider } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/context'
import type { Locale } from '../../i18n/locales'
import type { LoginResult } from '../../server/auth.functions'
import { dictionaries } from '../../test/render'
import { LoginForm } from './LoginForm'

/**
 * The real router, in memory. `/chat` is behind the session like the app's: with `hasSession` false it sends the browser back to
 * /login, which is what happens when the browser did not keep the cookie the sign-in set.
 */
function mount(signIn: () => Promise<LoginResult>, { hasSession, locale = 'es', target }: { hasSession: boolean; locale?: Locale; target?: string }) {
  const root = createRootRoute()
  const login = createRoute({
    getParentRoute: () => root,
    path: '/login',
    component: () => <LoginForm demoCustomers={[]} target={target} signIn={signIn} />,
  })
  const chat = createRoute({
    getParentRoute: () => root,
    path: '/chat',
    beforeLoad: () => {
      if (!hasSession) throw redirect({ to: '/login' })
    },
    component: () => <p>conversación</p>,
  })
  const router = createRouter({ routeTree: root.addChildren([login, chat]), history: createMemoryHistory({ initialEntries: ['/login'] }) })
  render(<I18nProvider locale={locale} messages={dictionaries[locale]}><RouterProvider router={router} /></I18nProvider>)
  return router
}

async function submit(locale: Locale = 'es') {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText(/^(Número de cliente)/), 'CLI-FIX0001')
  await user.type(screen.getByLabelText('PIN'), '123456')
  await user.click(screen.getByRole('button', { name: locale === 'es' ? 'Ingresar' : 'Entrar' }))
}

describe('the sign-in form when the API accepts the login', () => {
  it('goes on to the chat when the browser kept the session', async () => {
    const signIn = vi.fn(async (): Promise<LoginResult> => ({ ok: true }))
    const router = mount(signIn, { hasSession: true })
    await submit()
    await waitFor(() => expect(screen.getByText('conversación')).toBeTruthy())
    expect(router.state.location.pathname).toBe('/chat')
  })

  it('goes on to the page it came from, with its query', async () => {
    const router = mount(async () => ({ ok: true }), { hasSession: true, target: '/chat?x=1#foo' })
    await submit()
    await waitFor(() => expect(screen.getByText('conversación')).toBeTruthy())
    expect(router.state.location.search).toEqual({ x: 1 })
  })

  it.each(['https://evil.invalid', '//evil.invalid', '/\\evil.invalid', 'javascript:alert(1)', '/%252f/evil.invalid', '/@evil.invalid', '/nada', '/operador/cola'])(
    'sends %s to the chat, never off the site',
    async (target) => {
      const router = mount(async () => ({ ok: true }), { hasSession: true, target })
      await submit()
      await waitFor(() => expect(screen.getByText('conversación')).toBeTruthy())
      expect(router.state.location.pathname).toBe('/chat')
    },
  )

  it('does not hang on "Ingresando…" when the browser did not keep it: the button comes back, with a clear message', async () => {
    const signIn = vi.fn(async (): Promise<LoginResult> => ({ ok: true }))
    const router = mount(signIn, { hasSession: false })
    await submit()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/^Tu navegador no guardó la sesión/)
    const button = screen.getByRole('button', { name: 'Ingresar' }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
    expect(button.getAttribute('aria-busy')).toBeNull()
    expect(screen.queryByText('Ingresando…')).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
    expect(signIn).toHaveBeenCalledTimes(1)
  })

  it('says it in Portuguese too', async () => {
    mount(async () => ({ ok: true }), { hasSession: false, locale: 'pt' })
    await submit('pt')
    expect((await screen.findByRole('alert')).textContent).toMatch(/^Seu navegador não guardou a sessão/)
    expect((screen.getByRole('button', { name: 'Entrar' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('lets the person try again, and the message goes away while it tries', async () => {
    let calls = 0
    mount(async (): Promise<LoginResult> => (calls++, { ok: true }), { hasSession: false })
    await submit()
    await screen.findByRole('alert')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Ingresar' }))
    await waitFor(() => expect(calls).toBe(2))
    expect((await screen.findByRole('alert')).textContent).toMatch(/^Tu navegador no guardó la sesión/)
  })
})

describe('the sign-in form when the API refuses the login', () => {
  it('keeps its own messages: wrong PIN is not a cookie problem', async () => {
    mount(async () => ({ ok: false, status: 401 }), { hasSession: false })
    await submit()
    expect((await screen.findByRole('alert')).textContent).toBe('Número de cliente o PIN incorrectos.')
    expect((screen.getByRole('button', { name: 'Ingresar' }) as HTMLButtonElement).disabled).toBe(false)
  })
})

describe('the sign-in form when a field is wrong before anything is sent', () => {
  const field = (name: string) => document.querySelector(`input[name="${name}"]`) as HTMLInputElement

  async function submitWith(locale: Locale, customerId: string, pin: string) {
    const signIn = vi.fn(async (): Promise<LoginResult> => ({ ok: true }))
    mount(signIn, { hasSession: true, locale })
    const user = userEvent.setup()
    if (customerId) await user.type(await screen.findByLabelText(/^(Número de cliente)/), customerId)
    else await screen.findByLabelText(/^(Número de cliente)/)
    if (pin) await user.type(screen.getByLabelText('PIN'), pin)
    await user.click(screen.getByRole('button', { name: locale === 'es' ? 'Ingresar' : 'Entrar' }))
    expect(signIn).not.toHaveBeenCalled()
    return user
  }

  it.each([
    ['es', 'Falta el PIN de 6 dígitos.'],
    ['pt', 'Falta o PIN de 6 dígitos.'],
  ] as const)('an empty PIN is explained in the language of the page (%s), not in the browser\'s', async (locale, message) => {
    await submitWith(locale, 'CLI-FIX0001', '')
    expect(field('pin').validationMessage).toBe(message)
  })

  it.each([
    ['es', 'Falta el número de cliente.'],
    ['pt', 'Falta o número de cliente.'],
  ] as const)('an empty customer number too (%s)', async (locale, message) => {
    await submitWith(locale, '', '123456')
    expect(field('customer_id').validationMessage).toBe(message)
  })

  it('a short PIN is explained as well (jsdom does not flag a too-short text typed by a script, so the customer number\'s minLength is not covered here)', async () => {
    await submitWith('es', 'CLI-FIX0001', '123')
    expect(field('pin').validationMessage).toBe('El PIN tiene 6 dígitos.')
  })

  it('the message goes away as soon as the person types, so it never blocks a valid value', async () => {
    const user = await submitWith('es', 'CLI-FIX0001', '')
    expect(field('pin').validationMessage).not.toBe('')
    await user.type(screen.getByLabelText('PIN'), '123456')
    expect(field('pin').validity.valid).toBe(true)
    expect(field('pin').validationMessage).toBe('')
  })
})
