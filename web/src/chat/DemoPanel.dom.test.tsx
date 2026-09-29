import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithI18n } from '../test/render'
import { DemoPanel } from './DemoPanel'
import type { DemoScenario } from './types'

vi.mock('../server/demo.functions', () => ({ applyDemoFault: vi.fn(), getDemoTickets: async () => [], startScenario: vi.fn() }))

const scenario: DemoScenario = {
  id: 'normal_balance', path: 'normal', customer_id: 'CLI-FIX0001', language: 'es', fault: null, turns: ['¿Cuál es mi saldo?'], expect: ['AUTO_RESOLVE'],
  title: { en: 'Balance question', es: 'Consulta de saldo', pt: 'Consulta de saldo (PT)' },
  look_for: { en: 'Answered from verified data.', es: 'Se responde con datos verificados.', pt: 'Respondida com dados verificados.' },
}

const draw = (locale: 'es' | 'pt', scenarios = [scenario]) =>
  renderWithI18n(<DemoPanel scenarios={scenarios} sessionRef="s" pending={false} escalations={0} send={async () => null} onSessionChanged={async () => {}} onClose={() => {}} />, locale)

describe('DemoPanel', () => {
  it('shows each scenario in the language of the interface', () => {
    draw('pt')
    expect(screen.getByText('Consulta de saldo (PT)')).toBeTruthy()
    expect(screen.getByText('Respondida com dados verificados.')).toBeTruthy()
  })

  it('in Spanish it shows the Spanish', () => {
    draw('es')
    expect(screen.getByText('Consulta de saldo')).toBeTruthy()
    expect(screen.getByText('Se responde con datos verificados.')).toBeTruthy()
  })

  it('an API that predates Portuguese falls back to Spanish instead of showing nothing', () => {
    const old = { ...scenario, title: { en: 'x', es: 'Consulta de saldo' }, look_for: { en: 'x', es: 'Se responde.' } }
    draw('pt', [old])
    expect(screen.getByText('Consulta de saldo')).toBeTruthy()
  })
})
