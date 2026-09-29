import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ConversationProvider, useConversation } from './ConversationProvider'
import type { HistoryResult, Reply, SendResult } from './types'

const server = vi.hoisted(() => ({
  sendMessage: vi.fn(),
  getHistory: vi.fn(),
  getCase: vi.fn(),
}))
vi.mock('../server/chat.functions', () => server)

const reply = (over: Partial<Reply> = {}): Reply => ({
  trace_id: 'abc12345', disposition: 'AUTO_RESOLVE', response_text: 'Tu saldo es 10 USD.', language: 'es', category: 'resolved', ticket_id: null, latency_ms: 1, ...over,
})
const ok = (r: Reply = reply()): SendResult => ({ ok: true, reply: r })
const empty: HistoryResult = { ok: true, turns: [], cases: [] }

function Probe() {
  const c = useConversation()
  return (
    <div>
      <button type="button" onClick={() => void c.send('hola')}>send</button>
      <button type="button" onClick={() => c.retry(c.entries.find((e) => e.role === 'user')?.id ?? 0)}>retry</button>
      <button type="button" onClick={() => void c.reload()}>reload</button>
      <output data-testid="ended">{String(c.ended)}</output>
      <output data-testid="sending">{String(c.sending)}</output>
      <output data-testid="history-failed">{String(c.historyFailed)}</output>
      <ol>
        {c.entries.map((e) => (
          <li key={e.id} data-role={e.role} data-delivery={e.role === 'user' ? e.delivery : undefined} data-failure={e.role === 'user' ? e.failure : undefined}>
            {e.role === 'user' ? e.text : e.role === 'assistant' ? e.reply.response_text : e.note}
          </li>
        ))}
      </ol>
      <ul>{c.cases.map((row) => <li key={row.ref.ticketId} data-case={row.ref.ticketId}>{row.state.state === 'ready' ? row.state.status : row.state.state}</li>)}</ul>
    </div>
  )
}

const mount = (initial: HistoryResult = empty, sessionRef = 's1') =>
  render(<ConversationProvider sessionRef={sessionRef} initial={initial}><Probe /></ConversationProvider>)
const items = (role: string) => [...document.querySelectorAll(`li[data-role="${role}"]`)]

beforeEach(() => {
  server.sendMessage.mockReset()
  server.getHistory.mockReset()
  server.getCase.mockReset()
  server.getCase.mockResolvedValue({ ok: true, case: { ticket_id: 'T', status: 'open', message: null } })
})

describe('ConversationProvider', () => {
  it('starts from what the API kept, so a reload shows the conversation', () => {
    mount({ ok: true, cases: [], turns: [{ role: 'user', text: 'hola', at: 1 }, { role: 'assistant', reply: reply(), at: 2 }] })
    expect(items('user')[0].textContent).toBe('hola')
    expect(items('assistant')[0].textContent).toBe('Tu saldo es 10 USD.')
    expect(items('note')).toHaveLength(1)
  })

  it('a message is sent once, shown as sending, then sent, followed by the reply', async () => {
    let finish: (r: SendResult) => void = () => {}
    server.sendMessage.mockReturnValue(new Promise<SendResult>((resolve) => { finish = resolve }))
    mount()
    await userEvent.setup().click(screen.getByText('send'))
    expect(items('user')[0].getAttribute('data-delivery')).toBe('sending')
    expect(screen.getByTestId('sending').textContent).toBe('true')
    await act(async () => finish(ok()))
    expect(items('user')[0].getAttribute('data-delivery')).toBe('sent')
    expect(items('assistant')).toHaveLength(1)
    const call = server.sendMessage.mock.calls[0][0].data
    expect(call.message).toBe('hola')
    expect(call.key).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
  })

  it('a lost answer is uncertain, and the retry travels with the same key', async () => {
    server.sendMessage.mockResolvedValueOnce({ ok: false, failure: 'timeout' }).mockResolvedValueOnce(ok())
    mount()
    const user = userEvent.setup()
    await user.click(screen.getByText('send'))
    await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))
    await user.click(screen.getByText('retry'))
    await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('sent'))
    const [first, second] = server.sendMessage.mock.calls.map((c) => c[0].data)
    expect(second.key).toBe(first.key)
    expect(items('user')).toHaveLength(1) // the message is not duplicated
  })

  it('a 409 leaves the message as already processed, and reloading brings the API\'s conversation back', async () => {
    server.sendMessage.mockResolvedValue({ ok: false, failure: 'already_processed' })
    server.getHistory.mockResolvedValue({ ok: true, cases: [], turns: [{ role: 'user', text: 'hola', at: 1 }, { role: 'assistant', reply: reply({ response_text: 'La respuesta guardada.' }), at: 2 }] })
    mount()
    const user = userEvent.setup()
    await user.click(screen.getByText('send'))
    await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('processed'))
    await user.click(screen.getByText('reload'))
    await waitFor(() => expect(items('assistant')[0]?.textContent).toBe('La respuesta guardada.'))
    expect(items('user')).toHaveLength(1)
  })

  it('a session that ended stops the conversation; the message was not sent', async () => {
    server.sendMessage.mockResolvedValue({ ok: false, failure: 'session_expired' })
    mount()
    await userEvent.setup().click(screen.getByText('send'))
    await waitFor(() => expect(screen.getByTestId('ended').textContent).toBe('true'))
    expect(items('user')[0].getAttribute('data-delivery')).toBe('failed')
  })

  it('the cases are the handoffs with a number; each is asked for its status, once', async () => {
    const t = '55d09c14-2235-4c3c-8967-ccac61db9c50'
    server.getCase.mockResolvedValue({ ok: true, case: { ticket_id: t, status: 'claimed', message: null } })
    mount({ ok: true, cases: [], turns: [{ role: 'user', text: 'x', at: 1 }, { role: 'assistant', reply: reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: t }), at: 2 }] })
    await waitFor(() => expect(document.querySelector(`[data-case="${t}"]`)?.textContent).toBe('claimed'))
    expect(server.getCase).toHaveBeenCalledTimes(1)
  })

  it('news about a case in a reply asks for the statuses again', async () => {
    const t = 'T-0123456789'
    server.getCase.mockResolvedValue({ ok: true, case: { ticket_id: t, status: 'open', message: null } })
    server.sendMessage.mockResolvedValue(ok(reply({ response_text: 'Novedad de tu caso: un agente ya lo tomó.\n\nTu saldo es 10.' })))
    mount({ ok: true, cases: [], turns: [{ role: 'user', text: 'x', at: 1 }, { role: 'assistant', reply: reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: t }), at: 2 }] })
    await waitFor(() => expect(server.getCase).toHaveBeenCalledTimes(1))
    await userEvent.setup().click(screen.getByText('send'))
    await waitFor(() => expect(server.getCase).toHaveBeenCalledTimes(2))
  })

  it('a conversation that could not be read says so, and reloading brings it', async () => {
    server.getHistory.mockResolvedValue({ ok: true, cases: [], turns: [{ role: 'user', text: 'hola', at: 1 }] })
    mount({ ok: false, failure: 'unavailable' })
    expect(screen.getByTestId('history-failed').textContent).toBe('true')
    await userEvent.setup().click(screen.getByText('reload'))
    await waitFor(() => expect(screen.getByTestId('history-failed').textContent).toBe('false'))
    expect(items('user')[0].textContent).toBe('hola')
  })

  it('another session starts another conversation, and an answer that arrives for the old one is ignored', async () => {
    let finish: (r: SendResult) => void = () => {}
    server.sendMessage.mockReturnValue(new Promise<SendResult>((resolve) => { finish = resolve }))
    const view = mount({ ok: true, cases: [], turns: [{ role: 'user', text: 'vieja', at: 1 }] }, 's1')
    await userEvent.setup().click(screen.getByText('send'))
    view.rerender(<ConversationProvider sessionRef="s2" initial={empty}><Probe /></ConversationProvider>)
    expect(items('user')).toHaveLength(0)
    await act(async () => finish(ok()))
    expect(items('assistant')).toHaveLength(0)
    expect(screen.getByTestId('sending').textContent).toBe('false')
  })

  describe('a late answer never lands in the wrong place', () => {
    const late = <T,>() => {
      let done: (value: T) => void = () => {}
      const promise = new Promise<T>((resolve) => { done = resolve })
      return { promise, done }
    }
    const turns = (text: string): HistoryResult => ({ ok: true, cases: [], turns: [{ role: 'user', text, at: 1 }, { role: 'assistant', reply: reply({ response_text: `Respuesta a ${text}` }), at: 2 }] })

    it('a reload started in one session and answered in another is dropped', async () => {
      const a = late<HistoryResult>()
      server.getHistory.mockReturnValue(a.promise)
      const view = mount(turns('sesion A'), 's1')
      await userEvent.setup().click(screen.getByText('reload'))
      view.rerender(<ConversationProvider sessionRef="s2" initial={turns('sesion B')}><Probe /></ConversationProvider>)
      await act(async () => a.done(turns('vieja de A')))
      expect(items('user').map((e) => e.textContent)).toEqual(['sesion B'])
    })

    it('a reload that was in flight when a message was sent does not overwrite it with the old history', async () => {
      const old = late<HistoryResult>()
      server.getHistory.mockReturnValue(old.promise)
      server.sendMessage.mockResolvedValue(ok(reply({ response_text: 'La respuesta nueva.' })))
      mount(turns('vieja'))
      const user = userEvent.setup()
      await user.click(screen.getByText('reload'))
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('assistant').map((e) => e.textContent)).toContain('La respuesta nueva.'))
      await act(async () => old.done(turns('vieja')))
      expect(items('user').map((e) => e.textContent)).toEqual(['vieja', 'hola'])
      expect(items('assistant').map((e) => e.textContent)).toContain('La respuesta nueva.')
    })

    it('the status of a case asked in one session does not fill the same case of the next', async () => {
      const t = 'T-0123456789'
      const withCase: HistoryResult = { ok: true, cases: [], turns: [{ role: 'user', text: 'x', at: 1 }, { role: 'assistant', reply: reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: t }), at: 2 }] }
      const a = late<unknown>()
      const b = late<unknown>()
      server.getCase.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
      const view = mount(withCase, 's1')
      await waitFor(() => expect(server.getCase).toHaveBeenCalledTimes(1))
      view.rerender(<ConversationProvider sessionRef="s2" initial={withCase}><Probe /></ConversationProvider>)
      await waitFor(() => expect(server.getCase).toHaveBeenCalledTimes(2))
      await act(async () => a.done({ ok: true, case: { ticket_id: t, status: 'approved', message: null } }))
      expect(document.querySelector(`[data-case="${t}"]`)?.textContent).toBe('loading')
      await act(async () => b.done({ ok: true, case: { ticket_id: t, status: 'open', message: null } }))
      expect(document.querySelector(`[data-case="${t}"]`)?.textContent).toBe('open')
    })
  })

  describe('the cases and the 409 do not depend on the bounded history', () => {
    const t = '55d09c14-2235-4c3c-8967-ccac61db9c50'

    it('a case the history no longer has a turn for is still listed, from the API\'s own index', async () => {
      server.getCase.mockResolvedValue({ ok: true, case: { ticket_id: t, status: 'open', message: null } })
      mount({ ok: true, turns: [{ role: 'user', text: 'reciente', at: 5 }], cases: [{ ticketId: t, category: 'theft', at: 1 }] })
      await waitFor(() => expect(document.querySelector(`[data-case="${t}"]`)?.textContent).toBe('open'))
      expect(server.getCase).toHaveBeenCalledTimes(1)
    })

    it('a reload brings the index back too, and a case opened by hand is not lost by it', async () => {
      server.getCase.mockResolvedValue({ ok: true, case: { ticket_id: t, status: 'open', message: null } })
      server.getHistory.mockResolvedValue({ ok: true, turns: [], cases: [{ ticketId: t, category: 'theft', at: 1 }] })
      mount()
      await userEvent.setup().click(screen.getByText('reload'))
      await waitFor(() => expect(document.querySelector(`[data-case="${t}"]`)).not.toBeNull())
    })

    it('a 409 whose answer the API no longer has says so after the reload, instead of promising it', async () => {
      server.sendMessage.mockResolvedValue({ ok: false, failure: 'already_processed' })
      server.getHistory.mockResolvedValue({ ok: true, turns: [{ role: 'user', text: 'otra cosa', at: 1 }], cases: [] })
      mount()
      const user = userEvent.setup()
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[0].getAttribute('data-failure')).toBe('already_processed'))
      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(items('user').map((e) => e.getAttribute('data-failure'))).toContain('answer_gone'))
      expect(items('user').map((e) => e.textContent)).toEqual(['otra cosa', 'hola'])
    })

    it('a 409 whose answer the reload finds is simply shown', async () => {
      server.sendMessage.mockResolvedValue({ ok: false, failure: 'already_processed' })
      server.getHistory.mockResolvedValue({ ok: true, turns: [{ role: 'user', text: 'hola', at: 1 }, { role: 'assistant', reply: reply({ response_text: 'La guardada.' }), at: 2 }], cases: [] })
      mount()
      const user = userEvent.setup()
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[0].getAttribute('data-failure')).toBe('already_processed'))
      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(items('assistant')[0]?.textContent).toBe('La guardada.'))
      expect(items('user').map((e) => e.getAttribute('data-failure'))).toEqual([null])
    })
  })
})
