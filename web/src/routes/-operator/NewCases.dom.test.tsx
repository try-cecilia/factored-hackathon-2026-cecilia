import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect, type ReactElement } from 'react'
import { beforeEach, describe, expect, it } from 'vitest'
import { I18nProvider } from '../../i18n/context'
import type { QueueRow, Result } from '../../server/operator.functions'
import { dictionaries, renderWithI18n } from '../../test/render'
import { NewCasesAnnouncer, NewCasesBadge, NewCasesBar, NewCasesProvider, NewMark, useNewCases } from './NewCases'
import { SEEN_KEY, type SeenStore } from './seen'

const row = (id: string, status: QueueRow['desk']['status'] = 'open'): QueueRow => ({
  ticket_id: id, created_at: 1, category: 'fraud', priority: 'High', queue: 'fraud_ops', customer_id: 'C-1', country: 'México', language: 'es', request: 'r',
  desk: { status, operator: null, version: 0 },
})
const ok = (...ids: string[]): Result<QueueRow[]> => ({ ok: true, data: ids.map((id) => row(id)) })

function MarkAll() {
  const { markSeen } = useNewCases()
  return <button type="button" onClick={() => markSeen()}>marcar</button>
}
function Opens({ id }: { id: string }) {
  const { markSeen } = useNewCases()
  useEffect(() => markSeen([id]), [id, markSeen])
  return null
}
const Rows = ({ ids }: { ids: string[] }) => <ul>{ids.map((id) => <li key={id}>{id}<NewMark id={id} /></li>)}</ul>

// The tab's storage, in memory: a test injects it, so the code under test never has to name the browser's.
const memory = () => {
  const data: Record<string, string> = {}
  return { data, getItem: (key: string) => data[key] ?? null, setItem: (key: string, value: string) => void (data[key] = value) } satisfies SeenStore & { data: object }
}
let tab = memory()

const tree = (queue: Result<QueueRow[]>, ids: string[], extra?: ReactElement, store: () => SeenStore | undefined = () => tab) => (
  <NewCasesProvider queue={queue} store={store}>
    <NewCasesAnnouncer />
    <p data-testid="badge"><NewCasesBadge /></p>
    <Rows ids={ids} />
    <MarkAll />
    <NewCasesBar />
    {extra}
  </NewCasesProvider>
)
const page = (node: ReactElement, locale: 'es' | 'pt' = 'es') => <I18nProvider locale={locale} messages={dictionaries[locale]}>{node}</I18nProvider>
const status = () => screen.getByRole('status')

beforeEach(() => {
  tab = memory()
  document.title = 'Cola · Cecilai'
})

describe('new cases', () => {
  it('shows nothing on the first look: what is in the queue is the baseline', () => {
    renderWithI18n(tree(ok('a', 'b'), ['a', 'b']))
    expect(screen.getByTestId('badge').textContent).toBe('')
    expect(status().textContent).toBe('')
    expect(document.title).toBe('Cola · Cecilai')
    expect(screen.queryByText('Nuevo')).toBeNull()
  })

  it('a case that arrives is marked, counted, announced politely and put in the tab title', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b'])))
    expect(screen.getByTestId('badge').textContent).toBe('+1' + '1 caso nuevo')
    expect(screen.getByText('+1').getAttribute('aria-hidden')).toBe('true')
    await waitFor(() => expect(status().textContent).toBe('1 caso nuevo'))
    expect(status().getAttribute('aria-live')).toBe('polite')
    expect(document.title).toBe('(1) Cola · Cecilai')
    expect(screen.getByText('b').textContent).toBe('bNuevo')
    expect(screen.getByText('a').textContent).toBe('a')

    view.rerender(page(tree(ok('a', 'b', 'c', 'd'), ['a', 'b', 'c', 'd'])))
    await waitFor(() => expect(status().textContent).toBe('3 casos nuevos'))
    expect(document.title).toBe('(3) Cola · Cecilai')
  })

  it('the queue header says how many are new and has one button to be done with them, which is not itself a live region', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    expect(screen.queryByRole('button', { name: 'Marcar como vistos' })).toBeNull()
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b'])))
    const bar = screen.getByRole('button', { name: 'Marcar como vistos' }).parentElement!
    expect(bar.textContent).toBe('1 caso nuevoMarcar como vistos')
    expect(bar.closest('[aria-live]')).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Marcar como vistos' }))
    expect(screen.queryByRole('button', { name: 'Marcar como vistos' })).toBeNull()
  })

  it('speaks Portuguese to a Portuguese operator', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']), 'pt')
    view.rerender(page(tree(ok('a', 'b', 'c'), ['a', 'b', 'c']), 'pt'))
    await waitFor(() => expect(status().textContent).toBe('2 novos casos'))
    expect(screen.getAllByText('Novo')).toHaveLength(2)
  })

  it('does not take the focus when it announces', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    const button = screen.getByRole('button', { name: 'marcar' })
    await userEvent.setup().click(button)
    expect(document.activeElement).toBe(button)
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b'])))
    expect(document.activeElement).toBe(button)
  })

  it('marking them as seen clears the marks, the count, the announcement and the title', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b'])))
    await userEvent.setup().click(screen.getByRole('button', { name: 'marcar' }))
    expect(screen.getByTestId('badge').textContent).toBe('')
    expect(status().textContent).toBe('')
    expect(document.title).toBe('Cola · Cecilai')
    expect(screen.queryByText('Nuevo')).toBeNull()
  })

  it('does not announce again when the count goes down, and speaks again when it goes up', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    view.rerender(page(tree(ok('a', 'b', 'c'), ['a', 'b', 'c'])))
    await waitFor(() => expect(status().textContent).toBe('2 casos nuevos'))
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b']))) // c left the queue
    await waitFor(() => expect(status().textContent).toBe('2 casos nuevos'))
    expect(document.title).toBe('(1) Cola · Cecilai')
    view.rerender(page(tree(ok('a', 'b', 'e', 'f'), ['a', 'b', 'e', 'f'])))
    await waitFor(() => expect(status().textContent).toBe('3 casos nuevos'))
  })

  it('a rise back to a count already announced is announced again: the region is emptied, then says it', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    const heard: string[] = []
    new MutationObserver(() => heard.push(status().textContent ?? '')).observe(status(), { childList: true, characterData: true, subtree: true })
    view.rerender(page(tree(ok('a', 'b', 'c'), ['a', 'b', 'c'])))
    await waitFor(() => expect(status().textContent).toBe('2 casos nuevos'))
    view.rerender(page(tree(ok('a', 'b', 'c'), ['a', 'b', 'c'], <Opens id="b" />))) // one of them is opened: 1 new
    await waitFor(() => expect(document.title).toBe('(1) Cola · Cecilai'))
    view.rerender(page(tree(ok('a', 'b', 'c', 'd'), ['a', 'b', 'c', 'd'], <Opens id="b" />))) // another arrives: 2 again
    await waitFor(() => expect(document.title).toBe('(2) Cola · Cecilai'))
    await waitFor(() => expect(heard.filter((text) => text === '2 casos nuevos')).toHaveLength(2))
    expect(heard).toContain('') // and between the two the region was empty, which is what makes a screen reader read it again
    await waitFor(() => expect(status().textContent).toBe('2 casos nuevos'))
  })

  it('a case someone already decided is not new', () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    view.rerender(page(tree({ ok: true, data: [row('a'), row('b', 'approved')] }, ['a', 'b'])))
    expect(screen.getByTestId('badge').textContent).toBe('')
    expect(document.title).toBe('Cola · Cecilai')
  })

  it('opening a case marks it seen, and does not turn the rest of the queue into news', async () => {
    const view = renderWithI18n(tree(ok('a', 'b'), ['a', 'b'], <Opens id="a" />))
    expect(screen.getByTestId('badge').textContent).toBe('')
    view.rerender(page(tree(ok('a', 'b', 'c'), ['a', 'b', 'c'], <Opens id="a" />)))
    await waitFor(() => expect(status().textContent).toBe('1 caso nuevo'))
    view.rerender(page(tree(ok('a', 'b', 'c'), ['a', 'b', 'c'], <Opens id="c" />)))
    expect(screen.getByTestId('badge').textContent).toBe('')
    expect(document.title).toBe('Cola · Cecilai')
  })

  it('a failed read keeps what was counted', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b'])))
    view.rerender(page(tree({ ok: false, status: 503 }, ['a', 'b'])))
    expect(document.title).toBe('(1) Cola · Cecilai')
    await waitFor(() => expect(status().textContent).toBe('1 caso nuevo'))
  })

  it('remembers what was seen in the tab across a reload', () => {
    const first = renderWithI18n(tree(ok('a'), ['a']))
    first.rerender(page(tree(ok('a', 'b'), ['a', 'b'])))
    expect(JSON.parse(tab.data[SEEN_KEY] ?? 'null')).toEqual(['a'])
    first.unmount()
    // The tab reloads: b arrived while nobody had looked, so it is still new.
    renderWithI18n(tree(ok('a', 'b'), ['a', 'b']))
    expect(document.title).toBe('(1) Cola · Cecilai')
  })

  it('puts the count back when the router writes the title of another page, and takes it off with the console', async () => {
    const view = renderWithI18n(tree(ok('a'), ['a']))
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b'])))
    act(() => {
      document.title = 'Caso · Cecilai'
    })
    await waitFor(() => expect(document.title).toBe('(1) Caso · Cecilai'))
    view.unmount()
    expect(document.title).toBe('Caso · Cecilai')
  })

  it('a browser without storage still works, from an empty memory', () => {
    const none = () => undefined
    const view = renderWithI18n(tree(ok('a'), ['a'], undefined, none))
    view.rerender(page(tree(ok('a', 'b'), ['a', 'b'], undefined, none)))
    expect(document.title).toBe('(1) Cola · Cecilai')
  })
})
