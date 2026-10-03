import { Link } from '@tanstack/react-router'
import { useT } from '../i18n/context'
import { figures as F } from './figures'
import { demoEntry, sections } from './links'
import { useFigures } from './useFigures'

/** The claim, the way in, the four figures that back it, and Cecilia next to a conversation written by the code. */
export function Hero() {
  const t = useT()
  const f = useFigures()
  return (
    <section className="land-hero" aria-labelledby="land-title">
      <div className="land-hero__copy">
        <p className="land-hero__eyebrow"><span className="land-dot" aria-hidden="true" />{t('landing.hero.eyebrow')}</p>
        <h1 id="land-title" className="land-hero__title">{t('landing.hero.title')}</h1>
        <p className="land-hero__lead">{t('landing.hero.lead')}</p>
        <div className="land-hero__actions">
          <Link className="ui-btn ui-btn--primary ui-btn--lg land-cta" {...demoEntry}>
            <span>{t('landing.hero.tryDemo')}</span>
            <span className="land-cta__arrow" aria-hidden="true">→</span>
          </Link>
          <a className="ui-btn ui-btn--outline ui-btn--lg land-cta" href={`#${sections.results}`}>{t('landing.hero.seeEvaluation')}</a>
        </div>
        <p className="land-hero__note">{t('landing.hero.disclaimer')}</p>
        <ul className="land-strip" aria-label={t('landing.hero.strip.label')}>
          <li><strong>{f.n(F.offlineUnsafe)}/{f.n(F.offlineCases)}</strong> <span>{t('landing.hero.strip.unsafeOffline')}</span></li>
          <li><strong>{f.n(F.sonnetUnsafe)}/{f.n(F.liveCases)}</strong> <span>{t('landing.hero.strip.unsafeLive', { runs: f.n(F.liveRuns) })}</span></li>
          <li><strong>{f.pct(F.sonnetSafe)}</strong> <span>{t('landing.hero.strip.safeResolution')}</span></li>
          <li><strong>{f.n(F.sonnetP50)} s</strong> <span>{t('landing.hero.strip.latency')}</span></li>
        </ul>
      </div>
      <ConversationWindow />
    </section>
  )
}

/** The sky window: the account-savings conversation of the real templates, with its "Why?" chip. An illustration, not a control. */
function ConversationWindow() {
  const t = useT()
  const avatar = <img className="land-chat__avatar" src="/cecilia-avatar.png" alt="" width={26} height={26} />
  return (
    <figure className="land-window" aria-label={t('landing.hero.window.label')}>
      <img className="land-window__mascot" src="/cecilia-hero.png" alt={t('landing.mascotAlt')} width={420} height={420} />
      <div className="land-chat">
        <div className="land-chat__head">
          <span className="land-chat__title">{t('landing.hero.window.title')}</span>
          <span className="land-chat__badge">{t('landing.hero.window.badge')}</span>
        </div>
        <ol className="land-chat__log">
          <li className="land-chat__customer">{t('landing.hero.window.customer1')}</li>
          <li className="land-chat__cecilia">{avatar}<p>{t('landing.hero.window.cecilia1')}</p></li>
          <li className="land-chat__customer">{t('landing.hero.window.customer2')}</li>
          <li className="land-chat__cecilia">
            {avatar}
            <div className="land-chat__stack">
              <p>{t('landing.hero.window.cecilia2')}</p>
              <span className="land-chat__why"><span aria-hidden="true">ⓘ </span>{t('landing.hero.window.why')}</span>
            </div>
          </li>
        </ol>
      </div>
      <p className="land-window__verified"><span className="land-dot land-dot--success" aria-hidden="true" />{t('landing.hero.window.verified')}</p>
    </figure>
  )
}
