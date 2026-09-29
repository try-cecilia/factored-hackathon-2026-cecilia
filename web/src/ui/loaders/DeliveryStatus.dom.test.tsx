import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithI18n } from '../../test/render'
import { DeliveryStatus } from './DeliveryStatus'

describe('DeliveryStatus', () => {
  it('an uncertain send says so, explains that retrying is safe, and offers the retry', async () => {
    const onRetry = vi.fn()
    renderWithI18n(<DeliveryStatus status="uncertain" detail="Reintentar es seguro." onRetry={onRetry} />)
    expect(screen.getByText('Sin confirmar')).toBeTruthy()
    expect(screen.getByText('Reintentar es seguro.')).toBeTruthy()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('a message the API already has offers to load the conversation, never to send it again', async () => {
    const onReload = vi.fn()
    renderWithI18n(<DeliveryStatus status="processed" onRetry={() => {}} onReload={onReload} />)
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cargar la conversación' }))
    expect(onReload).toHaveBeenCalledOnce()
  })

  it('a sent message shows the time and no action; in Portuguese the words follow', () => {
    renderWithI18n(<DeliveryStatus status="sent" time="10:42" />, 'pt')
    expect(screen.getByText('Enviado · 10:42')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})
