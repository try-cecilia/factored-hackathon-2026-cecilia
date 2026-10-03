import type { MessageKey } from '../i18n/translate'
import { useT } from '../i18n/context'
import { figures as F } from './figures'
import { useFigures } from './useFigures'

const layers = ['model', 'api', 'data', 'web', 'evaluation', 'operations', 'interface'] as const

/** What it is built with, and the security controls inside it. */
export function Stack() {
  const t = useT()
  const f = useFigures()
  return (
    <section className="land-sec land-stack" aria-label={`${t('landing.stack.eyebrow')} · ${t('landing.security.eyebrow')}`}>
      <div className="land-in land-stack__in">
        <div>
          <h2 className="land-eyebrow">{t('landing.stack.eyebrow')}</h2>
          <dl className="land-lines">
            {layers.map((id) => (
              <div key={id}>
                <dt>{t(`landing.stack.${id}` as MessageKey)}</dt>
                <dd>{t(`landing.stack.${id}Value` as MessageKey)}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <h2 className="land-eyebrow">{t('landing.security.eyebrow')}</h2>
          <ul className="land-lines">
            <li>{t('landing.security.session', { bits: f.n(F.sessionTokenBits), minutes: f.n(F.sessionMinutes) })}</li>
            <li>{t('landing.security.roles', { roles: f.n(F.roles) })}</li>
            <li>{t('landing.security.masking')}</li>
            <li>{t('landing.security.csp')}</li>
            <li>{t('landing.security.supplyChain')}</li>
            <li>{t('landing.security.cookie')}</li>
            <li>{t('landing.security.attribution')}</li>
          </ul>
        </div>
      </div>
    </section>
  )
}
