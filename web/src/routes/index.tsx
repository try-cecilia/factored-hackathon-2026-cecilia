import { createFileRoute, Link } from '@tanstack/react-router'
import { useT } from '../i18n/context'
import { PublicShell } from '../shell/PublicShell'

export const Route = createFileRoute('/')({ component: Home })

function Home() {
  const t = useT()
  return (
    <PublicShell>
      <main className="hero" id="main">
        <div className="hero__copy">
          <h1>{t('home.titleLine1')}<br />{t('home.titleLine2')}</h1>
          <p className="pub__lead">{t('home.lead')}</p>
          {/* A link, so it is a real navigation; it wears the kit's button classes. */}
          <Link className="ui-btn ui-btn--primary ui-btn--lg" to="/login"><span>{t('home.signIn')}</span></Link>
        </div>
        <img className="hero__art" src="/cecilia-hero.png" alt="" width={480} height={480} />
      </main>
    </PublicShell>
  )
}
