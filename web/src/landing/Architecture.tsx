import type { MessageKey } from '../i18n/translate'
import { useT } from '../i18n/context'
import { figures as F } from './figures'
import { sections } from './links'
import { Eyebrow } from './parts'
import { useFigures } from './useFigures'

const steps = ['session', 'guards', 'model', 'tools', 'reply'] as const

/** One turn in five steps, the model's the only dark one, and the single action with effect underneath. */
export function Architecture() {
  const t = useT()
  const f = useFigures()
  const step = (id: (typeof steps)[number], part: 'tag' | 'title' | 'text') => t(`landing.architecture.steps.${id}.${part}` as MessageKey)
  return (
    <section id={sections.architecture} className="land-sec land-architecture" aria-labelledby="land-architecture">
      <div className="land-in">
        <div className="land-head land-head--split">
          <div>
            <Eyebrow>{t('landing.architecture.eyebrow')}</Eyebrow>
            <h2 id="land-architecture" className="land-title">{t('landing.architecture.title')}</h2>
          </div>
          <p className="land-head__aside">{t('landing.architecture.adr1')}<br />{t('landing.architecture.adr2')}</p>
        </div>
        <ol className="land-steps">
          {steps.map((id) => (
            <li key={id} className={id === 'model' ? 'land-step land-step--dark' : 'land-step'}>
              <span className="land-step__tag">{step(id, 'tag')}</span>
              <h3 className="land-step__title">{step(id, 'title')}</h3>
              <p className="land-step__text">{step(id, 'text')}</p>
            </li>
          ))}
        </ol>
        <div className="land-action">
          <h3 className="land-action__title">{t('landing.architecture.action.title')}</h3>
          <p className="land-action__text">{t('landing.architecture.action.text')}</p>
          <p className="land-action__basis">{t('landing.architecture.action.basis', { pending: f.n(F.pendingMovements), share: f.n(F.pendingShare) })}</p>
        </div>
      </div>
    </section>
  )
}
