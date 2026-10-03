import { useEffect, useState } from 'react'
import { useT } from '../../i18n/context'

const SEEN = 'cecilai.demo.bankHint'

const wasSeen = () => {
  try {
    return window.localStorage.getItem(SEEN) === '1'
  } catch {
    return false
  }
}
const markSeen = () => {
  try {
    window.localStorage.setItem(SEEN, '1')
  } catch {
    // A browser that keeps nothing shows the hint again next time: harmless.
  }
}

/**
 * The first time on the customer's side, a short line under "Cliente | Banco" says what Banco is. It goes once the visitor closes it
 * or opens Banco, and does not come back in this browser. Drawn only after mounting, so the server's HTML never carries it.
 */
export function BankHint({ view }: { view: 'customer' | 'bank' }) {
  const t = useT()
  const [shown, setShown] = useState(false)
  useEffect(() => {
    if (view === 'bank') markSeen()
    else setShown(!wasSeen())
  }, [view])
  if (!shown || view !== 'customer') return null
  const close = () => {
    markSeen()
    setShown(false)
  }
  return (
    <div className="demo-hint" role="note">
      <p>{t('demoMode.bar.bankHint')}</p>
      <button type="button" className="demo-hint__close" onClick={close}>{t('demoMode.bar.bankHintClose')}</button>
    </div>
  )
}
