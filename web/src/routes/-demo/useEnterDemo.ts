import { useNavigate, useRouter } from '@tanstack/react-router'
import { useState } from 'react'
import type { Translate } from '../../i18n/translate'
import type { DemoRole } from '../../server/demo-entry'
import { enterDemo, type EnterDemoResult } from '../../server/demo.functions'

/** Who the one-click entry signs in as when nothing says otherwise: "Varias cuentas y una tarjeta". */
export const DEFAULT_DEMO_ROLE: DemoRole = 'cuentas'

type Failure = Extract<EnterDemoResult, { ok: false }>

/**
 * The one-click entry, the same everywhere it is offered (the landing's "Probar la demo", the bar's and the bank's "Entrar otra vez"):
 * enterDemo signs in on the server as the role's test customer (POST, same origin, limited per address; the PIN never leaves the
 * server), every loader reads again with the new session, and the visitor goes to `to`. No dialog, no step in between.
 */
export function useEnterDemo() {
  const router = useRouter()
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)

  async function enter(role: DemoRole = DEFAULT_DEMO_ROLE, to: '/chat' | '/demo/banco' = '/chat'): Promise<boolean> {
    if (pending) return false
    setPending(true)
    setFailure(null)
    // An HTTP 404 (the demo console off) or a network error is a failure like any other: the visitor reads one fixed text.
    const result = await enterDemo({ data: { role } }).catch((): Failure => ({ ok: false, reason: 'failed' }))
    if (result.ok) {
      await router.invalidate()
      await navigate({ to })
    } else setFailure(result)
    setPending(false)
    return result.ok
  }

  return { enter, pending, failure }
}

/** What the visitor reads when entering did not work. */
export const entryFailureText = (t: Translate, failure: Failure) =>
  failure.reason === 'limited' ? t('demoMode.entry.errors.limited', { seconds: failure.retryAfter ?? 60 }) : t('demoMode.entry.errors.failed')
