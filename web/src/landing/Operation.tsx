import { useT } from '../i18n/context'
import { figures as F, liveRunDate } from './figures'
import { sections } from './links'
import { Eyebrow } from './parts'
import { useFigures } from './useFigures'

/** What one resolution costs and how long it takes, the caps and the load, and what happens when something fails. */
export function Operation() {
  const t = useT()
  const f = useFigures()
  const live = t('landing.operation.liveTrace', { cases: f.n(F.liveCases), date: f.shortDate(liveRunDate.iso) })
  return (
    <section id={sections.operation} className="land-sec land-operation" aria-labelledby="land-operation">
      <div className="land-in">
        <div className="land-head">
          <Eyebrow>{t('landing.operation.eyebrow')}</Eyebrow>
          <h2 id="land-operation" className="land-title land-title--full">{t('landing.operation.title')}</h2>
        </div>
        <ul className="land-metrics">
          <li><strong>US$ {f.n(F.sonnetCost)}</strong> <span>{t('landing.operation.costText')}</span> <small className="land-trace">{live}</small></li>
          <li><strong>{f.n(F.sonnetP50)} s</strong> <span>{t('landing.operation.latencyText', { p95: f.n(F.sonnetP95) })}</span> <small className="land-trace">{live}</small></li>
          <li><strong>US$ {f.n(F.sessionSpendCap)}</strong> <span>{t('landing.operation.capText')}</span> <small className="land-trace">{t('landing.operation.capTrace')}</small></li>
          <li>
            <strong>{f.n(F.loadChatsPerSecond)} / s</strong> <span>{t('landing.operation.loadText', { ms: f.n(F.loadRejectMs) })}</span>{' '}
            <small className="land-trace">{t('landing.operation.loadTrace', { slots: f.n(F.loadSlots), latency: f.seconds(F.loadModelMs) })}</small>
          </li>
        </ul>
        <div className="land-failover">
          <div className="land-failover__intro">
            <h3>{t('landing.operation.failures')}</h3>
            <p>{t('landing.operation.failuresText')}</p>
          </div>
          <ol className="land-failover__steps">
            <li><span className="land-failover__tag">{t('landing.operation.provider')}</span> <span>{t('landing.operation.providerText')}</span></li>
            <li><span className="land-failover__tag">{t('landing.operation.degraded')}</span> <span>{t('landing.operation.degradedText')}</span></li>
            <li><span className="land-failover__tag">{t('landing.operation.drift')}</span> <span>{t('landing.operation.driftText')}</span></li>
          </ol>
        </div>
      </div>
    </section>
  )
}
