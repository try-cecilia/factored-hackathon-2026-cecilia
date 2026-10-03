import { Link, useNavigate, useRouter } from '@tanstack/react-router'
import { useState } from 'react'
import { useT } from '../../i18n/context'
import { logout } from '../../server/auth.functions'
import type { DemoRole } from '../../server/demo-entry'
import { enterDemo } from '../../server/demo.functions'
import { minutesSeconds } from './expiry'
import { useDemoClock } from './useDemoClock'
import './demo-mode.css'

export type DemoBarProps = {
  /** Which side the visitor is on: the segmented control marks it and the text says it. */
  view: 'customer' | 'bank'
  /** The session the countdown belongs to, and the seconds the API says it has left. Null: not known (no countdown). */
  sessionRef: string | null
  expiresIn: number | null
  /** The test customer of this session, to enter again as the same one; null when it is not one of the dialog's (enter from the dialog). */
  role: DemoRole | null
  /**
   * The end is already known (the API said the session is gone, or the chat's own countdown reached 0): the bar says so whatever its
   * clock counts. Kept apart from `expiresIn` so it never moves the clock's end, which a new session must start afresh.
   */
  ended?: boolean
  /**
   * A message of the chat is on its way: the bank's side waits for its answer. Leaving would unmount the conversation that receives
   * it, and the turn would show only after a reload (the API keeps it, the chat read its history before).
   */
  holdBank?: boolean
  inert?: boolean
}

/** Where entering the demo starts: the home page with its dialog open. */
export const DEMO_ENTRY_HREF = '/?demo=entrar'

/**
 * The bar of the one-click demo, fixed on top of both sides (Paper "03 · Modo demo sin doble ingreso"): the DEMO chip, what is being
 * seen, "Customer | Bank" to switch with one click, and "Leave the demo". In the session's last three minutes it counts down and offers
 * to enter again; leaving signs the customer out, which also closes the bank's side, since that has no credential of its own.
 */
export function DemoBar({ view, sessionRef, expiresIn, role, ended = false, holdBank = false, inert }: DemoBarProps) {
  const t = useT()
  const router = useRouter()
  const navigate = useNavigate()
  const counted = useDemoClock(sessionRef, expiresIn)
  const clock: typeof counted = ended ? { state: 'over' } : counted
  const [busy, setBusy] = useState<'exit' | 'reenter' | null>(null)
  const [failed, setFailed] = useState(false)

  async function exit() {
    setBusy('exit')
    // The cookie goes whatever the API answers (auth.functions.ts); the home page is the way back in.
    await logout().catch(() => undefined)
    await navigate({ to: '/' })
    setBusy(null)
  }

  async function reenter() {
    if (!role) return void navigate({ href: DEMO_ENTRY_HREF })
    setBusy('reenter')
    setFailed(false)
    const result = await enterDemo({ data: { role } }).catch(() => null)
    if (result?.ok) {
      // A new session, with no cases yet: every loader reads again with it.
      await router.invalidate()
      await navigate({ to: view === 'bank' ? '/demo/banco' : '/chat' })
    } else setFailed(true)
    setBusy(null)
  }

  const warning = clock.state !== 'running'
  return (
    <div className="demo-bar" role="region" aria-label={t('demoMode.bar.label')} data-view={view} data-clock={clock.state} inert={inert ? true : undefined}>
      <div className="demo-bar__lead">
        <span className="demo-chip">{t('demoMode.badge')}</span>
        {warning ? (
          <span className="demo-bar__clock">
            <span aria-hidden="true">{clock.state === 'over' ? t('demoMode.bar.ended') : t('demoMode.bar.endsIn', { time: minutesSeconds(clock.seconds) })}</span>
            <button type="button" className="demo-bar__reenter" onClick={() => void reenter()} disabled={busy !== null}>
              {busy === 'reenter' ? t('demoMode.bar.reentering') : t('demoMode.bar.reenter')}
            </button>
          </span>
        ) : (
          <span className="demo-bar__text">{view === 'bank' ? t('demoMode.bar.bank') : t('demoMode.bar.customer')}</span>
        )}
        {holdBank && view === 'customer' && <span id="demo-bar-waiting" className="sr-only">{t('demoMode.bar.waiting')}</span>}
        <span className="sr-only" role="status">
          {failed ? t('demoMode.bar.reenterFailed') : clock.state === 'over' ? t('demoMode.bar.ended') : clock.state === 'warning' ? t('demoMode.bar.endsInMinutes', { n: Math.ceil(clock.seconds / 60) }) : ''}
        </span>
      </div>
      <div className="demo-bar__tools">
        <nav className="demo-seg" aria-label={t('demoMode.bar.switch')}>
          <Link to="/chat" aria-current={view === 'customer' ? 'page' : undefined}>{t('demoMode.bar.asCustomer')}</Link>
          {holdBank && view === 'customer' ? (
            <span role="link" aria-disabled="true" title={t('demoMode.bar.waiting')} aria-describedby="demo-bar-waiting">{t('demoMode.bar.asBank')}</span>
          ) : (
            <Link to="/demo/banco" aria-current={view === 'bank' ? 'page' : undefined}>{t('demoMode.bar.asBank')}</Link>
          )}
        </nav>
        <button type="button" className="demo-bar__exit" onClick={() => void exit()} disabled={busy !== null}>
          {busy === 'exit' ? t('demoMode.bar.exiting') : t('demoMode.bar.exit')}
        </button>
      </div>
    </div>
  )
}
