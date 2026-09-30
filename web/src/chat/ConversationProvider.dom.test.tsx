import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ConversationProvider, useConversation } from './ConversationProvider'
import type { CaseResult, HistoryResult, Reply, SendResult } from './types'

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
      <button type="button" onClick={() => c.retry([...c.entries].reverse().find((e) => e.role === 'user')?.id ?? 0)}>retry-last</button>
      <button type="button" onClick={() => void c.send('chau')}>send-b</button>
      <button type="button" onClick={() => c.retry(c.entries.find((e) => e.role === 'user' && e.text === 'chau')?.id ?? 0)}>retry-b</button>
      <button type="button" onClick={() => c.retry(c.entries.find((e) => e.role === 'user' && e.text === 'hola')?.id ?? 0)}>retry-a</button>
      <button type="button" onClick={() => void c.reload()}>reload</button>
      <button type="button" onClick={() => void c.refreshCase(c.cases[0]?.ref.ticketId ?? '')}>refresh-case</button>
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

  it('a history that does not have a message that was not answered does not drop it: it stays, with its key, and retrying sends the same one', async () => {
    server.sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce(ok())
    server.getHistory.mockResolvedValue(empty)
    mount({ ok: false, failure: 'unavailable' })
    const user = userEvent.setup()
    await user.click(screen.getByText('send'))
    await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))

    await user.click(screen.getByText('reload'))
    await waitFor(() => expect(screen.getByTestId('history-failed').textContent).toBe('false'))
    expect(items('user').map((e) => e.textContent)).toEqual(['hola'])
    expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain')

    await user.click(screen.getByText('retry'))
    await waitFor(() => expect(items('assistant')).toHaveLength(1))
    expect(server.sendMessage.mock.calls[1][0].data.key).toBe(server.sendMessage.mock.calls[0][0].data.key)
  })

  describe('two messages with the same text: what the history has does not say which one it is', () => {
    const yes: HistoryResult = { ok: true, cases: [], turns: [{ role: 'user', text: 'hola', at: 1 }, { role: 'assistant', reply: reply(), at: 2 }] }

    it('a confirmed message and a later one that was not answered: a history with one of them keeps the later one, with its key', async () => {
      server.sendMessage
        .mockResolvedValueOnce(ok())
        .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
        .mockResolvedValueOnce(ok(reply({ response_text: 'Otra vez.' })))
      server.getHistory.mockResolvedValue(yes)
      mount()
      const user = userEvent.setup()
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('assistant')).toHaveLength(1))
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[1].getAttribute('data-delivery')).toBe('uncertain'))

      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(items('note')).toHaveLength(1))
      expect(items('user').map((e) => e.getAttribute('data-delivery'))).toEqual(['sent', 'uncertain'])

      await user.click(screen.getByText('retry-last'))
      await waitFor(() => expect(server.sendMessage).toHaveBeenCalledTimes(3))
      expect(server.sendMessage.mock.calls[2][0].data.key).toBe(server.sendMessage.mock.calls[1][0].data.key)
      expect(server.sendMessage.mock.calls[2][0].data.key).not.toBe(server.sendMessage.mock.calls[0][0].data.key)
    })

    it('two that were not answered and a history with one of them: neither key is dropped', async () => {
      server.sendMessage
        .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
        .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      server.getHistory.mockResolvedValue(yes)
      mount()
      const user = userEvent.setup()
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[1].getAttribute('data-delivery')).toBe('uncertain'))

      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(items('note')).toHaveLength(1))
      expect(items('user').map((e) => e.getAttribute('data-delivery'))).toEqual(['sent', 'uncertain', 'uncertain'])
      expect(items('user').filter((e) => e.getAttribute('data-delivery') === 'uncertain')).toHaveLength(2)
    })

    it('an older message of the same text that was never loaded here: the one that was not answered still stays, with its key', async () => {
      server.sendMessage
        .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
        .mockResolvedValueOnce(ok(reply({ response_text: 'Otra vez.' })))
      server.getHistory.mockResolvedValue(yes)
      // The conversation could not be read when the page loaded: the older "hola" is only in the API.
      mount({ ok: false, failure: 'unavailable' })
      const user = userEvent.setup()
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))

      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(items('note')).toHaveLength(1))
      expect(items('user').map((e) => e.getAttribute('data-delivery'))).toEqual(['sent', 'uncertain'])

      await user.click(screen.getByText('retry-last'))
      await waitFor(() => expect(server.sendMessage).toHaveBeenCalledTimes(2))
      expect(server.sendMessage.mock.calls[1][0].data.key).toBe(server.sendMessage.mock.calls[0][0].data.key)
    })

    it('in a history of 40 entries, with the same text inside it, the message that was not answered stays with its key', async () => {
      const filler = Array.from({ length: 19 }, (_, i) => [
        { role: 'user' as const, text: `pregunta ${i}`, at: 2 * i },
        { role: 'assistant' as const, reply: reply(), at: 2 * i + 1 },
      ]).flat()
      const window: HistoryResult = { ok: true, cases: [], turns: [...yes.turns, ...filler] }
      expect(window.ok && window.turns.length).toBe(40)
      server.sendMessage.mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      server.getHistory.mockResolvedValue(window)
      mount({ ok: false, failure: 'unavailable' })
      const user = userEvent.setup()
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))
      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(items('note')).toHaveLength(1))
      expect(items('user').filter((e) => e.getAttribute('data-delivery') === 'uncertain')).toHaveLength(1)
    })

    it('a message the API has but whose answer is gone stays told so through the reloads that follow, and so does the next one', async () => {
      server.sendMessage
        .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
        .mockResolvedValueOnce({ ok: false, failure: 'already_processed' })
        .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
        .mockResolvedValueOnce({ ok: false, failure: 'already_processed' })
      server.getHistory.mockResolvedValue(empty)
      mount()
      const user = userEvent.setup()
      const failures = () => items('user').map((e) => e.getAttribute('data-failure'))
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))
      await user.click(screen.getByText('retry-a'))
      await waitFor(() => expect(failures()).toEqual(['already_processed']))
      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(failures()).toEqual(['answer_gone']))

      await user.click(screen.getByText('send-b'))
      await waitFor(() => expect(failures()).toEqual(['answer_gone', 'timeout']))
      await user.click(screen.getByText('retry-b'))
      await waitFor(() => expect(failures()).toEqual(['answer_gone', 'already_processed']))
      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(failures()).toEqual(['answer_gone', 'answer_gone']))
      await user.click(screen.getByText('reload'))
      await waitFor(() => expect(server.getHistory).toHaveBeenCalledTimes(3))
      expect(failures()).toEqual(['answer_gone', 'answer_gone'])
    })
  })

  it('a history that has the message does not take its place: the one that was not answered stays until it is retried', async () => {
    server.sendMessage
      .mockResolvedValueOnce({ ok: false, failure: 'timeout' })
      .mockResolvedValueOnce({ ok: false, failure: 'already_processed' })
    server.getHistory.mockResolvedValue({ ok: true, cases: [], turns: [{ role: 'user', text: 'hola', at: 1 }, { role: 'assistant', reply: reply(), at: 2 }] })
    mount({ ok: false, failure: 'unavailable' })
    const user = userEvent.setup()
    await user.click(screen.getByText('send'))
    await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))
    await user.click(screen.getByText('reload'))
    await waitFor(() => expect(items('assistant')).toHaveLength(1))
    // It cannot be told from what the history has: it stays, with its key, and retrying it settles it.
    expect(items('user').map((e) => e.getAttribute('data-delivery'))).toEqual(['sent', 'uncertain'])
    await user.click(screen.getByText('retry-last'))
    await waitFor(() => expect(items('user')[1].getAttribute('data-failure')).toBe('already_processed'))
    expect(server.sendMessage.mock.calls[1][0].data.key).toBe(server.sendMessage.mock.calls[0][0].data.key)
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

    it('a retry also invalidates a reload in flight: the late history does not erase the message or its key', async () => {
      const old = late<HistoryResult>()
      const retrying = late<SendResult>()
      server.sendMessage.mockResolvedValueOnce({ ok: false, failure: 'timeout' }).mockReturnValueOnce(retrying.promise)
      server.getHistory.mockReturnValue(old.promise)
      mount({ ok: false, failure: 'unavailable' })
      const user = userEvent.setup()
      await user.click(screen.getByText('send'))
      await waitFor(() => expect(items('user')[0].getAttribute('data-delivery')).toBe('uncertain'))
      await user.click(screen.getByText('reload'))
      await user.click(screen.getByText('retry'))
      await act(async () => old.done({ ok: true, turns: [], cases: [] })) // asked before the retry began, answered while it is still out
      expect(items('user').map((e) => e.textContent)).toEqual(['hola'])
      expect(screen.getByTestId('history-failed').textContent).toBe('true') // and it did not pretend the history was read
      await act(async () => retrying.done(ok(reply({ response_text: 'La respuesta del reintento.' }))))
      expect(items('assistant').map((e) => e.textContent)).toContain('La respuesta del reintento.')
      const [first, second] = server.sendMessage.mock.calls.map((c) => c[0].data)
      expect(second.key).toBe(first.key)
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

  it('an older read of a case that answers last does not replace a newer one', async () => {
    const escalated = reply({ disposition: 'ESCALATE', category: 'theft', ticket_id: 'T1', response_text: 'Voy a transferir tu caso.' })
    mount({ ok: true, cases: [], turns: [{ role: 'user', text: 'me robaron', at: 1 }, { role: 'assistant', reply: escalated, at: 2 }] })
    await screen.findByText('open')
    const answers: ((r: CaseResult) => void)[] = []
    server.getCase.mockImplementation(() => new Promise<CaseResult>((resolve) => { answers.push(resolve) }))
    const user = userEvent.setup()
    await user.click(screen.getByText('refresh-case'))
    await user.click(screen.getByText('refresh-case'))
    expect(answers).toHaveLength(2)
    await act(async () => answers[1]({ ok: true, case: { ticket_id: 'T1', status: 'approved', message: null } }))
    await act(async () => answers[0]({ ok: true, case: { ticket_id: 'T1', status: 'claimed', message: null } }))
    expect(document.querySelector('li[data-case="T1"]')?.textContent).toBe('approved')
  })
})
