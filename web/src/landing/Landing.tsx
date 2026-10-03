import { Link } from '@tanstack/react-router'
import { useT } from '../i18n/context'
import { PublicShell } from '../shell/PublicShell'
import { Ablation } from './Ablation'
import { Architecture } from './Architecture'
import { Baseline } from './Baseline'
import { Closing } from './Closing'
import { Hero } from './Hero'
import { sections, signInEntry } from './links'
import { Results } from './Results'
import { Science } from './Science'
import { Stack } from './Stack'
import './landing.css'

/** The public home: what Cecilia is, how one turn works, and every figure that backs it, each one with its source. */
export function Landing() {
  const t = useT()
  const nav = (
    <nav className="land-nav" aria-label={t('landing.nav.label')}>
      <a href={`#${sections.architecture}`}>{t('landing.nav.architecture')}</a>
      <a href={`#${sections.data}`}>{t('landing.nav.data')}</a>
      <a href={`#${sections.results}`}>{t('landing.nav.results')}</a>
    </nav>
  )
  const signIn = <Link className="ui-btn ui-btn--outline ui-btn--lg land-signin" {...signInEntry}>{t('landing.nav.signIn')}</Link>
  return (
    <PublicShell nav={nav} actions={signIn} className="land">
      <main id="main" className="land-main">
        <Hero />
        <Baseline />
        <Science />
        <Architecture />
        <Results />
        <Ablation />
        <Stack />
        <Closing />
      </main>
      <footer className="land-footer">
        <div className="land-in land-footer__in">
          <p>{t('landing.footer.note')}</p>
          <nav aria-label={t('landing.footer.label')}>
            <a href={`#${sections.security}`}>{t('landing.footer.security')}</a>
            <span aria-hidden="true"> · </span>
            <a href={`#${sections.results}`}>{t('landing.footer.evaluation')}</a>
          </nav>
        </div>
      </footer>
    </PublicShell>
  )
}
