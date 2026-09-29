import { createFileRoute, Link } from '@tanstack/react-router'
import { useT } from '../i18n/context'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'

export const Route = createFileRoute('/')({ component: Home })

function Home() {
  const t = useT()
  return (
    <main className="home" id="main">
      <span className="brand">
        <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
      </span>
      <h1>{t('home.titleLine1')}<br />{t('home.titleLine2')}</h1>
      <p className="lead">{t('home.lead')}</p>
      <Link className="btn btn-primary btn-lg" to="/login">{t('home.signIn')}</Link>
      <LanguageSwitcher />
    </main>
  )
}
