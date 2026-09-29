import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderWithI18n } from '../../test/render'
import { SidebarMenu, SidebarRowMenu, type SidebarMenuItem } from './SidebarMenu'

const items: SidebarMenuItem[] = [
  { id: 'rename', label: 'Renombrar' },
  { id: 'pin', label: 'Fijar' },
  { id: 'delete', label: 'Eliminar', danger: true },
]

function Row() {
  return (
    <div>
      <button type="button">Antes</button>
      <SidebarRowMenu name="Resumen del mes" items={items} onSelect={() => {}} />
      <button type="button">Después</button>
    </div>
  )
}

const trigger = () => screen.getByRole('button', { name: /Resumen del mes/ })
const menu = () => screen.queryByRole('menu')

async function openMenu() {
  const user = userEvent.setup()
  renderWithI18n(<Row />)
  await user.click(trigger())
  expect(menu()).not.toBeNull()
  // The first item takes the focus, as the menu button pattern asks.
  expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: 'Renombrar' }))
  return user
}

describe('row menu keyboard', () => {
  it('Escape closes the menu and gives the focus back to the trigger', async () => {
    const user = await openMenu()
    await user.keyboard('{Escape}')
    expect(menu()).toBeNull()
    expect(document.activeElement).toBe(trigger())
  })

  it('Tab closes the menu and moves on to the next control after the trigger', async () => {
    const user = await openMenu()
    await user.tab()
    expect(menu()).toBeNull()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Después' }))
  })

  it('Shift+Tab closes the menu and moves on to the previous control before the trigger', async () => {
    const user = await openMenu()
    await user.tab({ shift: true })
    expect(menu()).toBeNull()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Antes' }))
  })

  it('the arrows still move between the items and Enter selects the active one', async () => {
    const picked: string[] = []
    const user = userEvent.setup()
    renderWithI18n(<SidebarRowMenu name="Resumen del mes" items={items} onSelect={(id) => picked.push(id)} />)
    await user.click(trigger())
    await user.keyboard('{ArrowDown}')
    expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: 'Fijar' }))
    await user.keyboard('{Enter}')
    expect(picked).toEqual(['pin'])
    expect(menu()).toBeNull()
  })
})

describe('SidebarMenu on its own', () => {
  it('without onClose, Tab and Shift+Tab are not cancelled, so the focus can leave', () => {
    renderWithI18n(<SidebarMenu label="Opciones" items={items} onSelect={() => {}} />)
    const first = screen.getByRole('menuitem', { name: 'Renombrar' })
    // fireEvent returns false when the default action was prevented.
    expect(fireEvent.keyDown(first, { key: 'Tab' })).toBe(true)
    expect(fireEvent.keyDown(first, { key: 'Tab', shiftKey: true })).toBe(true)
  })

  it('reports the reason when it is asked to close', () => {
    const reasons: string[] = []
    renderWithI18n(<SidebarMenu label="Opciones" items={items} onSelect={() => {}} onClose={(reason) => reasons.push(reason)} />)
    const first = screen.getByRole('menuitem', { name: 'Renombrar' })
    fireEvent.keyDown(first, { key: 'Escape' })
    fireEvent.keyDown(first, { key: 'Tab' })
    expect(reasons).toEqual(['escape', 'tab'])
  })
})
