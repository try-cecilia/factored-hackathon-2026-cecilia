import { useId, useState } from 'react'
import { useT } from '../../i18n/context'
import { SCENARIO_OF, type DemoEntry, type DemoRole } from '../../server/demo-entry'
import './demo-mode.css'

type Props = {
  /** The test customers the kit offers (demoEntries): a card for each one. */
  entries: DemoEntry[]
  /** Loads a scenario by id, as the demo panel's card does (new session, then its first message); null while the panel is not ready. */
  run: ((id: string) => Promise<boolean>) | null
}

/**
 * What the visitor of the one-click demo sees on arriving in the chat: where they are, what they can try, and that the bank's side
 * comes after. Each card starts its situation with one click, through the demo panel's own scenarios (DemoPanel, onReady): the
 * customer of that scenario and its first message. Writing anything else in the composer works too.
 */
export function DemoWelcome({ entries, run }: Props) {
  const t = useT()
  const titleId = useId()
  const [starting, setStarting] = useState<DemoRole | null>(null)
  const [failed, setFailed] = useState(false)

  async function start(role: DemoRole) {
    if (!run || starting) return
    setStarting(role)
    setFailed(false)
    const ok = await run(SCENARIO_OF[role]).catch(() => false)
    if (!ok) setFailed(true)
    setStarting(null)
  }

  return (
    <section className="demo-welcome" aria-labelledby={titleId}>
      <img className="demo-welcome__avatar" src="/cecilia-avatar.png" alt="" width={72} height={72} />
      <h2 id={titleId}>{t('demoMode.welcome.title')}</h2>
      <p className="demo-welcome__body">{t('demoMode.welcome.body')}</p>
      <ul className="demo-welcome__cards" aria-label={t('demoMode.welcome.label')}>
        {entries.map(({ role }) => (
          <li key={role}>
            <button
              type="button"
              className="demo-welcome__card"
              onClick={() => void start(role)}
              disabled={!run || starting !== null}
              aria-busy={starting === role || undefined}
            >
              <strong>{t(`demoMode.welcome.cards.${role}.title`)}</strong>
              <span>{starting === role ? t('demoMode.welcome.starting') : t(`demoMode.welcome.cards.${role}.body`)}</span>
              <span className="demo-welcome__arrow" aria-hidden="true">→</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="demo-welcome__note" role={failed ? 'alert' : undefined}>{failed ? t('demoMode.welcome.failed') : t('demoMode.welcome.note')}</p>
    </section>
  )
}
