import { useT } from '../i18n/context'
import { figures as F } from './figures'
import { Eyebrow, FigureTable } from './parts'
import { useFigures } from './useFigures'

/** What each group of controls buys, on the gray block, beside three more pieces of evidence. */
export function Ablation() {
  const t = useT()
  const f = useFigures()
  const bad = ['bad', 'bad'] as const
  return (
    <section className="land-sec land-ablation" aria-labelledby="land-ablation">
      <div className="land-in land-ablation__in">
        <div className="land-ablation__main">
          <Eyebrow>{t('landing.ablation.eyebrow')}</Eyebrow>
          <h2 id="land-ablation" className="land-title land-title--sm">{t('landing.ablation.title', { bad: f.n(F.ablationNoneBad), all: f.n(F.ablationAllBad) })}</h2>
          <FigureTable
            caption={t('landing.ablation.caption')}
            columns={[t('landing.ablation.header', { cases: f.n(F.offlineCases) }), t('landing.ablation.ideal'), t('landing.ablation.bad')]}
            rows={[
              { label: t('landing.ablation.none'), cells: [f.pct(F.ablationNoneIdeal), f.pct(F.ablationNoneBad)], tones: [...bad] },
              { label: t('landing.ablation.identity'), cells: [f.pct(F.ablationIdentityIdeal), f.pct(F.ablationIdentityBad)], tones: [...bad] },
              { label: t('landing.ablation.templates'), cells: [f.pct(F.ablationTemplatesIdeal), f.pct(F.ablationTemplatesBad)], tones: [...bad] },
              { label: t('landing.ablation.all'), cells: [f.pct(F.ablationAllIdeal), f.pct(F.ablationAllBad)], strong: true, tones: ['good', 'good'] },
            ]}
          />
          <p className="land-footnote">{t('landing.ablation.note', { cases: f.n(F.ablationNeedPerson) })}</p>
        </div>
        <div className="land-ablation__more">
          <h2 className="land-eyebrow">{t('landing.evidence.eyebrow')}</h2>
          <ul className="land-evidence">
            <li className="land-evidence__wide"><strong>{f.n(F.heldoutCases)} · {f.n(F.heldoutUnsafe)}</strong> <span>{t('landing.evidence.heldoutText')}</span></li>
            <li><strong>{t('landing.evidence.redTeamValue', { hours: 1 /* README.md: "attacked the deployed demo for over an hour" */ })}</strong> <span>{t('landing.evidence.redTeamText')}</span></li>
            <li><strong>{t('landing.evidence.projectionValue', { contacts: f.n(F.projectedContacts) })}</strong> <span>{t('landing.evidence.projectionText', { hours: f.n(F.projectedHours) })}</span></li>
          </ul>
        </div>
      </div>
    </section>
  )
}
