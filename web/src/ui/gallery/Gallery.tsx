import { Link } from '@tanstack/react-router'
import { I18nProvider, useI18n, useT } from '../../i18n/context'
import { locales, localeNames, type Locale } from '../../i18n/locales'
import { LanguageSwitcher } from '../LanguageSwitcher'
import { LoadersGallery } from '../loaders/LoadersGallery'
import { MessagesGallery } from '../messages/MessagesGallery'
import { SidebarGallery } from '../sidebar/SidebarGallery'
import { TableGallery } from '../table/TableGallery'
import { ButtonGallery } from './ButtonGallery'
import { Section } from './Section'
import './Gallery.css'

const sections = ['buttons', 'language', 'loaders', 'sidebar', 'table', 'messages'] as const

function Sections() {
  const t = useT()
  return (
    <>
      <Section id="buttons" title={t('gallery.sections.buttons')}><ButtonGallery /></Section>
      <Section id="language" title={t('gallery.sections.language')}><LanguageSwitcher /></Section>
      <Section id="loaders" title={t('gallery.sections.loaders')}><LoadersGallery /></Section>
      <Section id="sidebar" title={t('gallery.sections.sidebar')}><SidebarGallery /></Section>
      <Section id="table" title={t('gallery.sections.table')}><TableGallery /></Section>
      <Section id="messages" title={t('gallery.sections.messages')}><MessagesGallery /></Section>
    </>
  )
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
              {sections.map((id) => <a key={id} href={`#${id}`}>{t(`gallery.sections.${id}`)}</a>)}
            </nav>
          </div>
        </header>
        <div className="gal__lang">
          {shown.map((code) => (
            <I18nProvider key={code} locale={code}>
              <div className="gal__lang" data-locale={code} lang={code}>
                {both && <p className="gal__lang-tag">{localeNames[code]}</p>}
                <Sections />
              </div>
            </I18nProvider>
          ))}
        </div>
      </div>
    </div>
  )
}
