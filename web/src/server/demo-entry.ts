import { PublicError } from './rpc-guard.ts'

// The one-click entry of the demo: which test customers it offers, as roles of the sandbox, each one a guided scenario the API
// already lists (api/demo.py). Free of framework code so a plain `node --test` can run it.

export const DEMO_ROLES = ['cuentas', 'pendiente', 'portugues'] as const
export type DemoRole = (typeof DEMO_ROLES)[number]

/** The scenario each role signs in as: its customer, its language and its fault (`clear_traces` for the pending transfer). */
export const SCENARIO_OF: Record<DemoRole, string> = {
  cuentas: 'normal_balance',
  pendiente: 'action_trace',
  portugues: 'normal_pt_arrears',
}

export type DemoEntry = { role: DemoRole; customer_id: string; language: string }

/** The roles whose scenario the API lists now, in the order of the dialog. A role without one is not offered. */
export function entriesOf(scenarios: readonly { id: string; customer_id: string; language: string }[]): DemoEntry[] {
  return DEMO_ROLES.flatMap((role) => {
    const found = scenarios.find((s) => s.id === SCENARIO_OF[role])
    return found ? [{ role, customer_id: found.customer_id, language: found.language }] : []
  })
}

export function parseRole(input: unknown): { role: DemoRole } {
  const { role } = (input ?? {}) as Record<string, unknown>
  if (!DEMO_ROLES.includes(role as DemoRole)) throw new PublicError('role is not valid')
  return { role: role as DemoRole }
}

/** The test customers of the one-click demo in a kit (getDemoKit), or none when it is off: only `console: true` turns it on. */
export const demoEntries = (kit: { enabled: boolean; console?: boolean; entries?: DemoEntry[] }): DemoEntry[] =>
  kit.enabled && kit.console === true ? kit.entries ?? [] : []
