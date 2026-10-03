import { Link } from '@tanstack/react-router'
import { useT } from '../i18n/context'
import { consoleEntry, demoEntry, signInEntry } from './links'

/** The way in, once more: Cecilia in her circle, the demo, and the sign-in for whoever has an account or a console key. */
export function Closing() {
  const t = useT()
  return (
    <section className="land-closing" aria-labelledby="land-closing">
      <div className="land-in land-closing__in">
        <img className="land-closing__mascot" src="/cecilia-hero.png" alt={t('landing.mascotAlt')} width={240} height={240} />
        <div className="land-closing__copy">
          <h2 id="land-closing" className="land-title">{t('landing.closing.title')}</h2>
          <p className="land-closing__lead">{t('landing.closing.lead')}</p>
        </div>
        <div className="land-closing__actions">
          <Link className="ui-btn ui-btn--primary ui-btn--lg land-cta land-cta--block" {...demoEntry}>
            <span>{t('landing.closing.enter')}</span>
            <span className="land-cta__arrow" aria-hidden="true">→</span>
          </Link>
          <p className="land-closing__links">
            {t('landing.closing.haveAccount')} <Link {...signInEntry}>{t('landing.closing.pinSignIn')}</Link>
            <span aria-hidden="true"> · </span>
            <Link {...consoleEntry}>{t('landing.closing.console')}</Link>
          </p>
        </div>
      </div>
    </section>
  )
}
