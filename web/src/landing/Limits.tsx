import { useT } from '../i18n/context'
import { figures as F } from './figures'
import { publicRepository, sections } from './links'
import { Eyebrow } from './parts'
import { useFigures } from './useFigures'

/** What the figures do not say: the black band of limits, each with its number. */
export function Limits() {
  const t = useT()
  const f = useFigures()
  const items = [
    [t('landing.limits.zero'), t('landing.limits.zeroText', { live: f.n(F.liveCases), liveBound: f.n(F.liveUpperBound), offline: f.n(F.offlineCases), offlineBound: f.n(F.offlineUpperBound) })],
    [t('landing.limits.sample'), t('landing.limits.sampleText', { live: f.n(F.liveCases), offline: f.n(F.offlineCases), runs: f.n(F.liveRuns), eligible: f.n(F.liveEligible), resolved: f.n(F.sonnetSafeResolved), safe: f.n(F.sonnetSafe), low: f.n(F.sonnetSafeLow), high: f.n(F.sonnetSafeHigh) })],
    [t('landing.limits.synthetic'), t('landing.limits.syntheticText')],
    [t('landing.limits.sandbox'), t('landing.limits.sandboxText')],
    [t('landing.limits.security'), t('landing.limits.securityText', { missing: f.n(F.asvsMissing) })],
    [t('landing.limits.instance'), t('landing.limits.instanceText', { memory: f.n(F.instanceMemoryMb), sample: f.n(F.demoCustomers), customers: f.n(F.customers) })],
  ]
  return (
    <section id={sections.limits} className="land-sec land-limits" aria-labelledby="land-limits">
      <div className="land-in land-limits__in">
        <div className="land-limits__intro">
          <Eyebrow>{t('landing.limits.eyebrow')}</Eyebrow>
          <h2 id="land-limits" className="land-title">{t('landing.limits.title')}</h2>
          <p className="land-limits__lead">{t('landing.limits.lead')}</p>
          {publicRepository && <a className="land-limits__all" href={`${publicRepository}/blob/main/LIMITATIONS.md`}>{t('landing.limits.all')} <span aria-hidden="true">→</span></a>}
        </div>
        <dl className="land-limits__list">
          {items.map(([title, text]) => (
            <div key={title}><dt>{title}</dt><dd>{text}</dd></div>
          ))}
        </dl>
      </div>
    </section>
  )
}
