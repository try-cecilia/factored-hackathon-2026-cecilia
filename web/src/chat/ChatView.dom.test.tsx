import { act, fireEvent, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Session } from '../server/auth.functions'
import { ShellProvider } from '../shell/ShellContext'
import { renderWithI18n } from '../test/render'
import { ChatView } from './ChatView'
import { ConversationProvider } from './ConversationProvider'
import type { HistoryResult } from './types'

// ChatLog asks for the clock's formatter once per render: counting those calls counts its renders.
const renders = vi.hoisted(() => ({ log: 0 }))
vi.mock('./clock', () => ({ useTimeParts: () => { renders.log += 1; return () => undefined } }))
const router = vi.hoisted(() => ({ navigate: vi.fn(), href: '/chat' }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => router.navigate, useLocation: () => ({ href: router.href }) }))
vi.mock('../server/chat.functions', () => ({ sendMessage: vi.fn(), getHistory: vi.fn(), getCase: vi.fn() }))

const session: Session = { customer_id: 'CLI-FIX0001', session_ref: 's1', segment: 'Premium', country: 'México', customer_status: 'Active', expires_at: 0, expires_in: 900 }
const history: HistoryResult = {
  ok: true,
  cases: [],
  turns: [
    { role: 'user', text: '¿Cuál es mi saldo?', at: 1 },
    { role: 'assistant', at: 2, reply: { trace_id: 'abc12345', disposition: 'AUTO_RESOLVE', response_text: 'Tu saldo es 10 USD.', language: 'es', category: 'resolved', ticket_id: null, latency_ms: 1 } },
  ],
}

beforeEach(() => {
  vi.useFakeTimers()
  Element.prototype.scrollIntoView = vi.fn()
  window.matchMedia = ((query: string) => ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia
  globalThis.ResizeObserver = class { observe() {} disconnect() {} unobserve() {} } as unknown as typeof ResizeObserver
})
afterEach(() => {
  vi.useRealTimers()
  router.navigate.mockReset()
  router.href = '/chat'
})

describe('ChatView', () => {
  it('the session countdown does not draw the conversation again before its notice, and the notice and the end still come', async () => {
    renderWithI18n(
      <ShellProvider value={{ showCase: () => {} }}>
        <ConversationProvider sessionRef="s1" initial={history}><ChatView session={session} /></ConversationProvider>
      </ShellProvider>,
    )
    await act(() => vi.advanceTimersByTimeAsync(0))
    const settled = renders.log
    expect(screen.getByText('Tu saldo es 10 USD.')).toBeTruthy()

    // Twelve minutes of five-second ticks with nothing to show: the log is not drawn again.
    await act(() => vi.advanceTimersByTimeAsync(12 * 60_000))
    expect(renders.log).toBe(settled)
    expect(screen.queryByText(/Tu sesión termina/)).toBeNull()

    // Two minutes left: the notice, in minutes.
    await act(() => vi.advanceTimersByTimeAsync(60_000))
    expect(screen.getByText('Tu sesión termina en 2 minutos.')).toBeTruthy()
    await act(() => vi.advanceTimersByTimeAsync(65_000))
    expect(screen.getByText('Tu sesión termina en 1 minuto.')).toBeTruthy()

    // Over: the note, the log ends with the sign-in message, the composer is off.
    await act(() => vi.advanceTimersByTimeAsync(60_000))
    expect(screen.getByText('Tu sesión venció')).toBeTruthy()
    expect(renders.log).toBeGreaterThan(settled)
  })

  it('another object of the same session, with the same time to go, does not start the countdown again: the end never moves later', async () => {
    let renew: (next: Session) => void = () => {}
    function Harness() {
      const [current, setCurrent] = useState(session)
      renew = setCurrent
      return (
        <ShellProvider value={{ showCase: () => {} }}>
          <ConversationProvider sessionRef="s1" initial={history}><ChatView session={current} /></ConversationProvider>
        </ShellProvider>
      )
    }
    renderWithI18n(<Harness />)
    await act(() => vi.advanceTimersByTimeAsync(600_000))
    // The route hands over a new object of the same session (a loader that ran again, with the same expires_in).
    await act(async () => renew({ ...session }))
    expect(screen.queryByText('Tu sesión venció')).toBeNull()

    await act(() => vi.advanceTimersByTimeAsync(301_000))
    expect(screen.getByText('Tu sesión venció')).toBeTruthy()
  })

  it('signing in again after the session ended comes back to the page it was on, with its query and fragment', async () => {
    router.href = '/chat?x=1#foo'
    renderWithI18n(
      <ShellProvider value={{ showCase: () => {} }}>
        <ConversationProvider sessionRef="s1" initial={history}><ChatView session={session} /></ConversationProvider>
      </ShellProvider>,
    )
    await act(() => vi.advanceTimersByTimeAsync(15 * 60_000 + 5_000))
    expect(screen.getByText('Tu sesión venció')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Ingresar de nuevo/ }))
    expect(router.navigate).toHaveBeenCalledWith({ to: '/login', search: { redirect: '/chat?x=1#foo', motivo: 'expired' }, replace: true })
  })
})
