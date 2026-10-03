import { useT } from '../i18n/context'
import { figures as F } from './figures'
import { useFigures } from './useFigures'

/** What the organizer's contact-center data says about this motive, before any line of the assistant. */
export function Baseline() {
  const t = useT()
  const f = useFigures()
  return (
    <section className="land-baseline" aria-labelledby="land-baseline">
      <div className="land-in land-baseline__in">
        <h2 id="land-baseline" className="land-eyebrow land-eyebrow--muted">{t('landing.baseline.title')}</h2>
        <ul className="land-baseline__list">
          <li><strong>{f.pct(F.contactShare)}</strong> <span>{t('landing.baseline.contacts', { contacts: f.n(F.contactsThousands) })}</span></li>
          <li><strong>≈{f.n(F.humanSeconds)} s</strong> <span>{t('landing.baseline.humanTime', { queue: f.n(F.queueSeconds), call: f.n(F.callSeconds) })}</span></li>
          <li><strong>{f.n(F.csat)} / 5</strong> <span>{t('landing.baseline.csat', { fcr: f.n(F.firstContact) })}</span></li>
          <li><strong>≈{f.n(F.agentHours)} h</strong> <span>{t('landing.baseline.hours', { contacts: f.n(F.medianContacts) })}</span></li>
        </ul>
      </div>
    </section>
  )
}
