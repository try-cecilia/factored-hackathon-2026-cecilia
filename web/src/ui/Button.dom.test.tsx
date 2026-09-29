import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button, IconButton } from './Button'

// A loading button must not submit its form: dropping the click handler does not cancel the native submit of a
// `type="submit"` button, so the button has to be truly disabled while it loads.

function Form({ loading, submit, click, icon }: { loading: boolean; submit: () => void; click?: () => void; icon?: boolean }) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <input aria-label="PIN" />
      {icon ? (
        <IconButton type="submit" label="Enviar" icon={<span />} loading={loading} onClick={click} />
      ) : (
        <Button type="submit" loading={loading} onClick={click}>Ingresar</Button>
      )}
    </form>
  )
}

describe.each([
  ['Button', false],
  ['IconButton', true],
])('%s while loading', (_name, icon) => {
  const target = () => screen.getByRole('button')

  it('does not submit the form on click', async () => {
    const submit = vi.fn()
    const click = vi.fn()
    render(<Form loading submit={submit} click={click} icon={icon} />)
    await userEvent.setup().click(target())
    expect(submit).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
  })

  it('does not submit with Enter or Space, even if it had the focus when the loading began', async () => {
    const submit = vi.fn()
    const user = userEvent.setup()
    const view = render(<Form loading={false} submit={submit} icon={icon} />)
    target().focus()
    view.rerender(<Form loading submit={submit} icon={icon} />)
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(submit).not.toHaveBeenCalled()
  })

  it('does not submit with Enter typed in a field of the form', async () => {
    const submit = vi.fn()
    const user = userEvent.setup()
    render(<Form loading submit={submit} icon={icon} />)
    await user.click(screen.getByLabelText('PIN'))
    await user.keyboard('{Enter}')
    expect(submit).not.toHaveBeenCalled()
  })

  it('is disabled and busy for assistive technology, and keeps its loading look', () => {
    render(<Form loading submit={() => {}} icon={icon} />)
    expect((target() as HTMLButtonElement).disabled).toBe(true)
    expect(target().getAttribute('aria-busy')).toBe('true')
    expect(target().getAttribute('aria-disabled')).toBe('true')
    expect(target().classList.contains('ui-btn--loading')).toBe(true)
  })
})

describe('Button when not loading', () => {
  it('submits with a click, with Enter and with Space', async () => {
    const submit = vi.fn()
    const user = userEvent.setup()
    render(<Form loading={false} submit={submit} />)
    await user.click(screen.getByRole('button'))
    screen.getByRole('button').focus()
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(submit).toHaveBeenCalledTimes(3)
  })

  it('is neither busy nor aria-disabled, and a plain disabled button is disabled', () => {
    const view = render(<Button>Ok</Button>)
    const button = () => screen.getByRole('button') as HTMLButtonElement
    expect(button().disabled).toBe(false)
    expect(button().hasAttribute('aria-busy')).toBe(false)
    expect(button().hasAttribute('aria-disabled')).toBe(false)
    view.rerender(<Button disabled>Ok</Button>)
    expect(button().disabled).toBe(true)
  })
})
