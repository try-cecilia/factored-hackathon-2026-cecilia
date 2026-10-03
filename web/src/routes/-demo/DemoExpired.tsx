import { useT } from '../../i18n/context'
import type { DemoRole } from '../../server/demo-entry'
import { Button } from '../../ui'
import { DEFAULT_DEMO_ROLE, useEnterDemo } from './useEnterDemo'

/**
 * The bank's side once the session is over (15 minutes from the entry, or "Salir" in another tab): it has no credential of its own,
 * so it says the demo ended and enters again straight away as the same test customer, a new session with no cases yet.
 */
export function DemoExpired({ role }: { role: DemoRole | null }) {
  const t = useT()
  const entry = useEnterDemo()
  return (
    <div className="op-notice demo-expired" role="alert">
      <h2>{t('demoMode.desk.expired.title')}</h2>
      <p>{t('demoMode.desk.expired.body')}</p>
      {entry.failure && <p className="op-danger">{t('demoMode.bar.reenterFailed')}</p>}
      <Button size="sm" loading={entry.pending} onClick={() => void entry.enter(role ?? DEFAULT_DEMO_ROLE, '/demo/banco')}>
        {entry.pending ? t('demoMode.bar.reentering') : t('demoMode.bar.reenter')}
      </Button>
    </div>
  )
}
