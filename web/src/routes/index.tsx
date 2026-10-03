import { createFileRoute, Link } from '@tanstack/react-router'
import { useT } from '../i18n/context'
import { demoEntries } from '../server/demo-entry'
import { getDemoKit, type DemoKit } from '../server/demo.functions'
import { PublicShell } from '../shell/PublicShell'
import { EnterDemoButton } from './-demo/EnterDemo'

export const Route = createFileRoute('/')({
  // `?demo=entrar` (DEMO_ENTRY_HREF) opens the one-click demo's dialog on arrival.
  validateSearch: (search: Record<string, unknown>): { demo?: 'entrar' } => (search.demo === 'entrar' ? { demo: 'entrar' } : {}),
  // Only the one-click demo's button waits for the kit; without the sandbox it is { enabled: false } and there is no button.
  loader: () => getDemoKit().catch((): DemoKit => ({ enabled: false })),
  component: Home,
})

function Home() {
  const t = useT()
  const kit = Route.useLoaderData()
  const { demo } = Route.useSearch()
  return (
    <PublicShell>
      <main className="hero" id="main">
        <div className="hero__copy">
          <h1>{t('home.titleLine1')}<br />{t('home.titleLine2')}</h1>
          <p className="pub__lead">{t('home.lead')}</p>
          <div className="hero__actions">
            {/* A link, so it is a real navigation; it wears the kit's button classes. */}
            <Link className="ui-btn ui-btn--primary ui-btn--lg" to="/login"><span>{t('home.signIn')}</span></Link>
            <EnterDemoButton entries={demoEntries(kit)} initiallyOpen={demo === 'entrar'} />
          </div>
        </div>
        <img className="hero__art" src="/cecilia-hero.png" alt="" width={480} height={480} />
      </main>
    </PublicShell>
  )
}
