import { useT } from '../i18n/context'
import { TARGET_MINUTES } from '../routes/-operator/sla'
import { figures as F } from './figures'
import { sections } from './links'
import { Eyebrow } from './parts'
import { useFigures } from './useFigures'

/** The other side: a mock of the queue, what reaches the person, and the projection, marked as one. */
export function Console() {
  const t = useT()
  const f = useFigures()
  // A mock: the waits are example values, not measurements. The targets are the console's own, a demo proposal (sla.ts).
  const target = { security: TARGET_MINUTES.security, regulatory: TARGET_MINUTES.regulatory / 60, service: TARGET_MINUTES.service / 60 }
  const rows = [
    { kind: t('landing.console.queue.security'), reason: t('landing.console.queue.securityCase'), wait: '19 min', target: `${target.security}m`, late: true },
    { kind: t('landing.console.queue.regulatory'), reason: t('landing.console.queue.regulatoryCase'), wait: '48 min', target: `${target.regulatory}h` },
    { kind: t('landing.console.queue.service'), reason: t('landing.console.queue.serviceCase'), wait: '1 h 10', target: `${target.service}h` },
  ]
  return (
    <section id={sections.console} className="land-sec land-console" aria-labelledby="land-console">
      <div className="land-in">
        <div className="land-head">
          <Eyebrow>{t('landing.console.eyebrow')}</Eyebrow>
          <h2 id="land-console" className="land-title land-title--wide">{t('landing.console.title')}</h2>
        </div>
        <div className="land-console__body">
          <figure className="land-queue">
            <div className="land-queue__head" aria-hidden="true">
              <span className="land-queue__title">{t('landing.console.queue.title')}</span>
              <span className="land-queue__columns">{t('landing.console.queue.columns')}</span>
            </div>
            <table className="land-queue__table">
              <caption className="sr-only">{t('landing.console.queue.caption')}</caption>
              <thead className="sr-only">
                <tr>
                  <th scope="col">{t('landing.console.queue.kind')}</th>
                  <th scope="col">{t('landing.console.queue.case')}</th>
                  <th scope="col">{t('landing.console.queue.wait')}</th>
                  <th scope="col">{t('landing.console.queue.target')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.kind} className={row.late ? 'land-queue__late' : undefined}>
                    <td className="land-queue__kind">{row.kind}</td>
                    <th scope="row">{row.reason}</th>
                    <td className="land-queue__wait">{row.wait}</td>
                    <td className="land-queue__target">{row.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <figcaption className="land-queue__note">
              {t('landing.console.queue.note', target)}
            </figcaption>
          </figure>
          <ol className="land-points">
            <li>
              <span className="land-points__n" aria-hidden="true">01</span>
              <div><h3>{t('landing.console.urgent')}</h3><p>{t('landing.console.urgentText', { minutes: target.security })}</p></div>
            </li>
            <li>
              <span className="land-points__n" aria-hidden="true">02</span>
              <div>
                <h3>{t('landing.console.complete')}</h3>
                <p>{t('landing.console.completeText', { ideal: f.n(F.idealComplete), keyword: f.n(F.keywordComplete) })}</p>
                <p className="land-trace">{t('landing.console.completeTrace', { cases: f.n(F.offlineCases) })}</p>
              </div>
            </li>
            <li>
              <span className="land-points__n" aria-hidden="true">03</span>
              <div><h3>{t('landing.console.back')}</h3><p>{t('landing.console.backText')}</p></div>
            </li>
          </ol>
        </div>
        <div className="land-projection">
          <div className="land-projection__label">
            <p className="land-projection__tag">{t('landing.console.projection.label')}</p>
            <p>{t('landing.console.projection.lead')}</p>
          </div>
          <ul className="land-projection__figures">
            <li><strong>≈{f.n(F.projectedContacts)}</strong> <span>{t('landing.console.projection.contactsText', { total: f.n(F.textContacts) })}</span></li>
            <li><strong>≈{f.n(F.projectedHours)} h</strong> <span>{t('landing.console.projection.hoursText')}</span></li>
            <li><strong>{f.n(F.queueSeconds)} s</strong> <span>{t('landing.console.projection.waitText')}</span></li>
          </ul>
          <p className="land-projection__note">{t('landing.console.projection.note', { floor: f.n(F.projectedFloor) })}</p>
        </div>
      </div>
    </section>
  )
}
