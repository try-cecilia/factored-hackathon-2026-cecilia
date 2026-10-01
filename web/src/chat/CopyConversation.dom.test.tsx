import { act, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithI18n } from '../test/render'
import { ConversationProvider } from './ConversationProvider'
import { CopyConversation } from './CopyConversation'
import type { HistoryResult } from './types'

vi.mock('../server/chat.functions', () => ({
  sendMessage: vi.fn(),
  getHistory: vi.fn(),
  getCase: async () => ({ ok: true, case: { ticket_id: 'CASE-0042', status: 'claimed', message: null } }),
}))

const at = Date.UTC(2026, 9, 1, 15, 38)
const reply = (response_text: string, extra: Record<string, unknown> = {}) => ({
  trace_id: 'trace-9f8e7d6c', disposition: 'AUTO_RESOLVE' as const, response_text, language: 'es', category: 'balance', ticket_id: null, latency_ms: 1, ...extra,
})
const talked: HistoryResult = {
  ok: true,
  cases: [],
  turns: [
    { role: 'user', text: 'Mis últimos movimientos', at },
    { role: 'assistant', at: at + 1, reply: reply('Estos son tus movimientos:\n- 15/01/2024 · Transferencia · −40.00 USD (Cuenta Ahorro ···0010)\n- 14/01/2024 · Pago · −5.00 USD') },
    { role: 'user', text: 'No reconozco un cargo', at: at + 2 },
    { role: 'assistant', at: at + 3, reply: reply('Pasé tu consulta a una persona del equipo.', { disposition: 'ESCALATE', category: 'fraud', ticket_id: 'CASE-0042' }) },
  ],
}
const empty: HistoryResult = { ok: true, cases: [], turns: [] }

async function draw(history: HistoryResult, locale: 'es' | 'pt' = 'es') {
  await act(async () => {
    renderWithI18n(<ConversationProvider sessionRef="s1" initial={history}><CopyConversation /></ConversationProvider>, locale)
  })
}
const button = (name: RegExp) => screen.getByRole('button', { name }) as HTMLButtonElement
const status = () => screen.getByRole('status').textContent

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('CopyConversation', () => {
  it('is off while the conversation is empty', async () => {
    await draw(empty)
    expect(button(/Copiar conversación/).disabled).toBe(true)
  })

  it('copies the whole conversation, in order, as the customer sees it, and says so', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await draw(talked)
    expect(button(/Copiar conversación/).disabled).toBe(false)
    expect(status()).toBe('')

    await user.click(button(/Copiar conversación/))
    const copied = (await navigator.clipboard.readText()).split('\n')
    expect(copied[0]).toMatch(/^Conversación con Cecilia · \d\d\/\d\d\/2026$/)
    expect(copied.slice(1).map((line) => line.replace(/^\[\d\d:\d\d\] /, ''))).toEqual([
      'Tú: Mis últimos movimientos',
      'Cecilia: Estos son tus movimientos:',
      '- 15/01/2024 · Transferencia · −40.00 USD (Cuenta Ahorro ···0010)',
      '- 14/01/2024 · Pago · −5.00 USD',
      'Tú: No reconozco un cargo',
      'Cecilia: Pasé tu consulta a una persona del equipo.',
      expect.stringMatching(/^Posible fraude · .+ · #CASE-0042$/),
    ])
    expect(copied.join('\n')).not.toMatch(/trace-9f8e7d6c|AUTO_RESOLVE|ESCALATE/)

    expect(status()).toBe('Conversación copiada')
    expect(screen.getAllByText('Conversación copiada')).toHaveLength(2) // the one for the screen reader and the one for the eye
    await act(() => vi.advanceTimersByTimeAsync(2600))
    expect(status()).toBe('')
    expect(screen.queryByText('Conversación copiada')).toBeNull()
  })

  it('a clipboard that refuses is told, not swallowed', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await draw(talked)
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new DOMException('denied', 'NotAllowedError'))

    await user.click(button(/Copiar conversación/))
    expect(status()).toBe('No se pudo copiar')
    expect(screen.getAllByText('No se pudo copiar')).toHaveLength(2)
    expect(screen.queryByText('Conversación copiada')).toBeNull()
    await act(() => vi.advanceTimersByTimeAsync(2600))
    expect(status()).toBe('')
  })

  it('a browser with no clipboard (plain http) says it could not copy', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await draw(talked)
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    await user.click(button(/Copiar conversación/))
    expect(status()).toBe('No se pudo copiar')
  })

  it('in Portuguese the button, the notice and the copied text are Portuguese', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await draw(talked, 'pt')
    await user.click(button(/Copiar conversa/))
    const copied = (await navigator.clipboard.readText()).split('\n')
    expect(copied[0]).toMatch(/^Conversa com a Cecilia · \d\d\/\d\d\/2026$/)
    expect(copied[1]).toMatch(/^\[\d\d:\d\d\] Você: Mis últimos movimientos$/)
    expect(copied[2]).toMatch(/^\[\d\d:\d\d\] Cecilia: Estos son/)
    expect(status()).toBe('Conversa copiada')
  })

  it('in Portuguese a refusal is told in Portuguese', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await draw(talked, 'pt')
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))
    await user.click(button(/Copiar conversa/))
    expect(status()).toBe('Não foi possível copiar')
  })
})
