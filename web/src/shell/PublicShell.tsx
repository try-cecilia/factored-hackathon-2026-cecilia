import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useT } from '../i18n/context'
import { LanguageSwitcher } from '../ui'
import './PublicShell.css'

/** The wordmark: the mascot on its sky tile and "cecilai". A link home unless `plain`. */
export function Brand({ plain }: { plain?: boolean }) {
  const t = useT()
  const mark = (
    <>
      <span className="brand__mark" aria-hidden="true"><img src="/cecilia-avatar.png" alt="" width={18} height={18} /></span>
      <span className="brand__word">cecilai</span>
    </>
  )
  return plain ? (
    <span className="brand">{mark}</span>
  ) : (
    <Link className="brand" to="/" aria-label={t('common.brandHome')}>{mark}</Link>
  )
}

/** The frame of the pages before the customer signs in: the wordmark and the language switcher on top, the page below. */
export function PublicShell({ children }: { children: ReactNode }) {
  const t = useT()
  return (
    <div className="pub">
      <a className="skip" href="#main">{t('common.skipToContent')}</a>
      <header className="pub__bar">
        <Brand />
        <LanguageSwitcher />
      </header>
      {children}
    </div>
  )
}
