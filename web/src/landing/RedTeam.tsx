import type { MessageKey } from '../i18n/translate'
import { useT } from '../i18n/context'
import { figures as F, redTeamDate } from './figures'
import { sections } from './links'
import { Eyebrow } from './parts'
import { useFigures } from './useFigures'

const failures = ['otherData', 'unconfirmedTrace', 'expiredSession', 'injection', 'load'] as const
const controls = ['signOut', 'crossSite', 'noCache', 'lockout', 'rateLimit'] as const

/** Security put to the test: the human red team on the deployed demo, beside the ASVS level 1 count. */
export function RedTeam() {
  const t = useT()
  const f = useFigures()
  const asvs = [
    { key: 'met', figure: F.asvsMet },
    { key: 'partial', figure: F.asvsPartial },
    { key: 'notApplicable', figure: F.asvsNotApplicable },
    { key: 'missing', figure: F.asvsMissing },
  ] as const
  return (
    <section id={sections.security} className="land-sec land-redteam" aria-labelledby="land-redteam">
      <div className="land-in">
        <div className="land-head">
          <Eyebrow>{t('landing.redTeam.eyebrow')}</Eyebrow>
          <h2 id="land-redteam" className="land-title land-title--full">{t('landing.redTeam.title', { minutes: f.n(F.redTeamMinutes) })}</h2>
        </div>
        <div className="land-redteam__cards">
          <article className="land-panel land-panel--wide" aria-labelledby="land-redteam-label">
            <div className="land-panel__meta">
              <h3 id="land-redteam-label">{t('landing.redTeam.label')}</h3>
              <span>{f.shortDate(redTeamDate.iso)}</span>
            </div>
            <ul className="land-panel__figures">
              <li><strong>{f.n(F.redTeamTurns)}</strong> <span>{t('landing.redTeam.turns')}</span></li>
              <li><strong>{f.n(F.redTeamSessions)}</strong> <span>{t('landing.redTeam.sessions')}</span></li>
              <li><strong>US$ {f.n(F.redTeamCost)}</strong> <span>{t('landing.redTeam.cost')}</span></li>
            </ul>
            <dl className="land-panel__rows" aria-label={t('landing.redTeam.failuresLabel')}>
              {failures.map((id) => (
                <div key={id}><dt>{t(`landing.redTeam.${id}` as MessageKey, { chats: f.n(F.redTeamMaxChats) })}</dt><dd>{f.n(F.redTeamFailures)}</dd></div>
              ))}
            </dl>
            <p className="land-panel__note">{t('landing.redTeam.note', { open: f.n(F.redTeamOpen) })}</p>
          </article>
          <article className="land-panel" aria-labelledby="land-asvs-label">
            <div className="land-panel__meta">
              <h3 id="land-asvs-label">{t('landing.redTeam.asvs')}</h3>
              <span>{t('landing.redTeam.requirements', { total: f.n(F.asvsTotal) })}</span>
            </div>
            <div className="land-asvs">
              <div className="land-asvs__bar" aria-hidden="true">
                {asvs.map(({ key, figure }) => <span key={key} className={`land-asvs__${key}`} style={{ flexGrow: figure.value }} />)}
              </div>
              <ul className="land-asvs__counts">
                {asvs.map(({ key, figure }) => (
                  <li key={key} className={key === 'missing' ? 'land-asvs__missing-count' : undefined}>
                    <strong>{f.n(figure)}</strong> <span>{t(`landing.redTeam.${key}` as MessageKey)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <ul className="land-panel__list">
              {controls.map((id) => (
                <li key={id}>{t(`landing.redTeam.${id}` as MessageKey, { attempts: f.n(F.pinAttempts), minutes: f.n(F.pinLockoutMinutes) })}</li>
              ))}
            </ul>
            <p className="land-panel__note">{t('landing.redTeam.asvsNote')}</p>
          </article>
        </div>
      </div>
    </section>
  )
}
