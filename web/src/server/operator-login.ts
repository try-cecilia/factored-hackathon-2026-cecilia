// The decision behind the operator forms, kept free of framework code so a plain `node --test` can run it.
// The keys arrive in a form post, go to the two probes and, when they check out, come back in the outcome for the
// server to store. The redirect target and the flash code are the only things that may reach the browser.
import { sameOriginPath } from './safe-path.ts'

export const MAX_KEY_LENGTH = 200
export const DEFAULT_LANDING = '/operador/cola'

export type ProbeResult = { ok: true; data: unknown } | { ok: false; status: number }
export type KeyProbe = (key: string) => Promise<ProbeResult>

export type OperatorKeys = { adminKey: string; operatorKey?: string; operator?: string }
export type FormOutcome =
  | { ok: true; to: string; keys: OperatorKeys }
  | { ok: false; to: string; flash: string }

const text = (form: FormData, name: string) => {
  const value = form.get(name)
  return typeof value === 'string' ? value.trim() : ''
}

const ownerOf = (result: ProbeResult) =>
  result.ok && typeof (result.data as { operator?: unknown } | null)?.operator === 'string'
    ? (result.data as { operator: string }).operator
    : undefined

/** Login form: a read key, and optionally an operator key. Any failure goes back to the form with a flash code. */
export async function loginFromForm(form: FormData, probes: { admin: KeyProbe; operator: KeyProbe }): Promise<FormOutcome> {
  const target = sameOriginPath(text(form, 'redirect'))
  const back = target ? `/operador/login?redirect=${encodeURIComponent(target)}` : '/operador/login'
  const adminKey = text(form, 'admin_key')
  const operatorKey = text(form, 'operator_key')
  if (!adminKey) return { ok: false, to: back, flash: 'admin_missing' }
  if (adminKey.length > MAX_KEY_LENGTH || operatorKey.length > MAX_KEY_LENGTH) return { ok: false, to: back, flash: 'key_invalid' }

  const admin = await probes.admin(adminKey)
  if (!admin.ok) return { ok: false, to: back, flash: `admin_${admin.status}` }
  if (!operatorKey) return { ok: true, to: target ?? DEFAULT_LANDING, keys: { adminKey } }

  const operator = await probes.operator(operatorKey)
  if (!operator.ok) return { ok: false, to: back, flash: `operator_${operator.status}` }
  return { ok: true, to: target ?? DEFAULT_LANDING, keys: { adminKey, operatorKey, operator: ownerOf(operator) } }
}

/** "Add your operator key" form, used from inside a read-only session. */
export async function operatorKeyFromForm(
  form: FormData,
  probe: KeyProbe,
): Promise<{ ok: true; to: string; operatorKey: string; operator?: string } | { ok: false; to: string; flash: string }> {
  const to = sameOriginPath(text(form, 'redirect')) ?? DEFAULT_LANDING
  const operatorKey = text(form, 'operator_key')
  if (!operatorKey) return { ok: false, to, flash: 'operator_missing' }
  if (operatorKey.length > MAX_KEY_LENGTH) return { ok: false, to, flash: 'key_invalid' }
  const result = await probe(operatorKey)
  if (!result.ok) return { ok: false, to, flash: `operator_${result.status}` }
  return { ok: true, to, operatorKey, operator: ownerOf(result) }
}
