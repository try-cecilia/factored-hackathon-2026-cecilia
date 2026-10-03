import { useNavigate, useRouter } from '@tanstack/react-router'
import { useState } from 'react'
import { useT } from '../../i18n/context'
import type { DemoRole } from '../../server/demo-entry'
import { enterDemo } from '../../server/demo.functions'
import { Button } from '../../ui'
import { DEMO_ENTRY_HREF } from './DemoBar'

/**
 * The bank's side once the session is over (15 minutes from the entry, or "Salir" in another tab): it has no credential of its own,
 * so it says the demo ended and offers to enter again as the same test customer, a new session with no cases yet.
 */
export function DemoExpired({ role }: { role: DemoRole | null }) {
  const t = useT()
  const router = useRouter()
  const navigate = useNavigate()
  const [entering, setEntering] = useState(false)
  const [failed, setFailed] = useState(false)

  async function again() {
    if (!role) return void navigate({ href: DEMO_ENTRY_HREF })
    setEntering(true)
    setFailed(false)
    const result = await enterDemo({ data: { role } }).catch(() => null)
    if (result?.ok) {
      await router.invalidate()
      await navigate({ to: '/demo/banco' })
    } else setFailed(true)
    setEntering(false)
  }

  return (
    <div className="op-notice demo-expired" role="alert">
      <h2>{t('demoMode.desk.expired.title')}</h2>
      <p>{t('demoMode.desk.expired.body')}</p>
      {failed && <p className="op-danger">{t('demoMode.bar.reenterFailed')}</p>}
      <Button size="sm" loading={entering} onClick={() => void again()}>{entering ? t('demoMode.bar.reentering') : t('demoMode.bar.reenter')}</Button>
    </div>
  )
}
