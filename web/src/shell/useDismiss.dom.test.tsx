import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLayoutEffect, useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { useDismiss } from './useDismiss'

// The panel is a drawer: closed it is inert, as the shell makes it. `elsewhere` is what the caller does while it closes.
function Harness({ onClosing, fallback }: { onClosing?: () => void; fallback?: () => HTMLElement | null }) {
  const [open, setOpen] = useState(false)
  const panel = useRef<HTMLDivElement>(null)
  useDismiss(open, true, () => setOpen(false), panel, fallback)
  // A layout effect runs before the passive cleanup of the hook, like a caller that moves the focus in the same commit.
  useLayoutEffect(() => { if (!open) onClosing?.() }, [open, onClosing])
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Abrir</button>
      <button type="button">Otro</button>
      <div ref={panel} inert={!open}>
        <button type="button" onClick={() => setOpen(false)}>Cerrar</button>
        <button type="button">Dentro</button>
      </div>
    </>
  )
}

describe('useDismiss gives the focus back to what opened the panel', () => {
  it('on Escape', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cerrar' }))
    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(opener)
  })

  it('when its own button closes it', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    await user.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(document.activeElement).toBe(opener)
  })

  it('when a click outside closes it and the focus is lost to the page', async () => {
    const user = userEvent.setup()
    function Scrimmed() {
      const [open, setOpen] = useState(false)
      const panel = useRef<HTMLDivElement>(null)
      useDismiss(open, true, () => setOpen(false), panel)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Abrir</button>
          {open && <button type="button" tabIndex={-1} aria-label="Fondo" onClick={() => setOpen(false)} />}
          <div ref={panel} inert={!open}><button type="button">Dentro</button></div>
        </>
      )
    }
    render(<Scrimmed />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    await user.click(screen.getByRole('button', { name: 'Fondo' }))
    expect(document.activeElement).toBe(opener)
  })

  it('when the focus was left in the panel as it closed', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    screen.getByRole('button', { name: 'Dentro', hidden: true }).focus()
    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(opener)
  })

  it('and when the opener cannot take it, to the fallback', async () => {
    const user = userEvent.setup()
    render(<Harness fallback={() => screen.getByRole('button', { name: 'Otro' })} />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    opener.setAttribute('inert', '')
    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Otro' }))
  })
})

describe('useDismiss keeps a focus that the caller has already put outside the panel', () => {
  it('on the element the caller chose, while the panel closes', async () => {
    const user = userEvent.setup()
    render(<Harness onClosing={() => screen.getByRole('button', { name: 'Otro' }).focus()} />)
    await user.click(screen.getByRole('button', { name: 'Abrir' }))
    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Otro' }))
  })

  it('but not one that went away (a removed element leaves the focus on the page, which goes back to the opener)', async () => {
    const user = userEvent.setup()
    const gone = document.createElement('button')
    document.body.append(gone)
    render(<Harness onClosing={() => { gone.focus(); gone.remove() }} />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(opener)
  })

  it('but not one that is itself behind an inert ancestor', async () => {
    const user = userEvent.setup()
    const behind = document.createElement('div')
    const inner = document.createElement('button')
    behind.append(inner)
    document.body.append(behind)
    render(<Harness onClosing={() => { inner.focus(); behind.setAttribute('inert', '') }} />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(opener)
  })

  it('and the listener is removed all the same', async () => {
    const user = userEvent.setup()
    const removed = vi.spyOn(document, 'removeEventListener')
    render(<Harness onClosing={() => screen.getByRole('button', { name: 'Otro' }).focus()} />)
    await user.click(screen.getByRole('button', { name: 'Abrir' }))
    await user.keyboard('{Escape}')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Otro' }))
    expect(removed.mock.calls.some(([type]) => type === 'keydown')).toBe(true)
    removed.mockRestore()
  })
})
