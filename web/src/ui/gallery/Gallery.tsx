import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { I18nProvider, useI18n, useT } from '../../i18n/context'
import { es } from '../../i18n/es'
import { locales, localeNames, type Locale } from '../../i18n/locales'
import { pt } from '../../i18n/pt'
import { LanguageSwitcher } from '../LanguageSwitcher'
import { LoadersGallery } from '../loaders/LoadersGallery'
import { MessagesGallery } from '../messages/MessagesGallery'
import { SidebarGallery } from '../sidebar/SidebarGallery'
import { TableGallery } from '../table/TableGallery'
import { ButtonGallery } from './ButtonGallery'
import { Section } from './Section'
import './Gallery.css'

// The whole kit in both languages: the full dictionaries, only in the gallery's own chunk (the pages load theirs by area).
const dictionaries = { es, pt }

const sections = ['buttons', 'language', 'loaders', 'sidebar', 'table', 'messages'] as const

const bodies: Record<(typeof sections)[number], () => ReactNode> = {
  buttons: () => <ButtonGallery />,
  language: () => <LanguageSwitcher />,
  loaders: () => <LoadersGallery />,
  sidebar: () => <SidebarGallery />,
  table: () => <TableGallery />,
  messages: () => <MessagesGallery />,
}

/** Anchors are `<language>-<section>` so the two languages of `?both=1` never share an id. */
function Sections({ code }: { code: Locale }) {
  const t = useT()
  return sections.map((id) => (
    <Section key={id} id={`${code}-${id}`} title={t(`gallery.sections.${id}`)}>{bodies[id]()}</Section>
  ))
}

/** `/dev/ui`: every component in every variant and state. With `?both=1` it draws the whole kit once per language. */
export function Gallery({ both }: { both: boolean }) {
  const { locale } = useI18n()
  const t = useT()
  const shown: Locale[] = both ? [...locales] : [locale]
  return (
    <div className="gal">
      <div className="gal__inner">
        <header className="gal__head">
          <p className="gal__eyebrow">/dev/ui</p>
          <h1 className="gal__title">{t('gallery.title')}</h1>
          <p className="gal__lead">{t('gallery.lead')}</p>
          <div className="gal__bar">
            <LanguageSwitcher />
            <Link to="/dev/ui" search={both ? {} : { both: 1 }} className="gal__caption">
              {both ? t('gallery.oneLanguage') : t('gallery.bothLanguages')}
            </Link>
            <nav className="gal__nav" aria-label={t('gallery.title')}>
              {sections.map((id) => <a key={id} href={`#${shown[0]}-${id}`}>{t(`gallery.sections.${id}`)}</a>)}
            </nav>
          </div>
        </header>
        <div className="gal__lang">
          {shown.map((code) => (
            <I18nProvider key={code} locale={code} messages={dictionaries[code]}>
              <div className="gal__lang" data-locale={code} lang={code}>
                {both && <p className="gal__lang-tag">{localeNames[code]}</p>}
                <Sections code={code} />
              </div>
            </I18nProvider>
          ))}
        </div>
      </div>
    </div>
  )
}
