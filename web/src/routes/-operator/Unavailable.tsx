import { useRouter } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import { Button } from '../../ui'

/** The whole console failed to load (the browser could not reach the BFF): say it and offer to read again. */
export function Unavailable({ reset }: { reset?: () => void }) {
  const t = useT()
  const router = useRouter()
  return (
    <div className="op">
      <main className="op-unavailable">
        <div className="op-notice" role="alert">
          <p>{t('operator.unavailable')}</p>
          <Button variant="ghost" tinted size="sm" onClick={() => { reset?.(); void router.invalidate() }}>{t('operator.retry')}</Button>
        </div>
      </main>
    </div>
  )
}
