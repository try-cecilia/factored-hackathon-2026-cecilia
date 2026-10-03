import { useT } from '../i18n/context'
import { figures as F, liveRunDate } from './figures'
import { sections } from './links'
import { Eyebrow, FigureTable } from './parts'
import { useFigures } from './useFigures'

/** The black block: the offline table (three variants of the model) beside the live one (two real models). */
export function Results() {
  const t = useT()
  const f = useFigures()
  const unsafe = `${f.n(F.offlineUnsafe)}/${f.n(F.offlineCases)}`
  const notApplicable = <><span aria-hidden="true">—</span><span className="sr-only">{t('landing.results.notApplicable')}</span></>
  const runs = (values: number[]) => values.join(' · ')
  return (
    <section id={sections.results} className="land-sec land-results" aria-labelledby="land-results">
      <div className="land-in">
        <div className="land-head land-head--split">
          <div>
            <Eyebrow>{t('landing.results.eyebrow')}</Eyebrow>
            <h2 id="land-results" className="land-title">{t('landing.results.title', { offline: f.n(F.offlineCases), live: f.n(F.liveCases) })}</h2>
          </div>
          <p className="land-head__aside">{t('landing.results.note', { types: f.n(F.caseTypes), cells: f.n(F.countrySegmentCells) })}</p>
        </div>
        <div className="land-results__tables">
          <FigureTable
            tone="dark"
            caption={t('landing.results.offline.caption')}
            columns={[t('landing.results.offline.header', { cases: f.n(F.offlineCases) }), t('landing.results.offline.keyword'), t('landing.results.offline.ideal'), t('landing.results.offline.adversarial')]}
            rows={[
              { label: t('landing.results.offline.safeAuto'), cells: [f.pct(F.keywordSafe), f.pct(F.idealSafe), f.pct(F.adversarialSafe)] },
              { label: t('landing.results.offline.recall'), cells: [f.pct(F.keywordRecall), f.pct(F.idealRecall), f.pct(F.adversarialRecall)] },
              { label: t('landing.results.offline.missed'), cells: [f.n(F.keywordMissed), f.n(F.idealMissed), f.n(F.adversarialMissed)] },
              { label: t('landing.results.offline.complete'), cells: [f.pct(F.keywordComplete), f.pct(F.idealComplete), f.pct(F.adversarialComplete)] },
              { label: t('landing.results.offline.unsafe'), cells: [unsafe, unsafe, unsafe], strong: true, tones: [undefined, 'good', 'good'] },
              { label: t('landing.results.offline.records'), cells: [notApplicable, f.n(F.offlineRecordsToModel), f.n(F.offlineRecordsToModel)] },
              {
                label: t('landing.results.offline.latency'),
                cells: [
                  `${f.n(F.keywordLatencyP50)} / ${f.n(F.keywordLatencyP95)}`,
                  `${f.n(F.idealLatencyP50)} / ${f.n(F.idealLatencyP95)}`,
                  `${f.n(F.adversarialLatencyP50)} / ${f.n(F.adversarialLatencyP95)}`,
                ],
              },
            ]}
          />
          <FigureTable
            tone="dark"
            caption={t('landing.results.live.caption')}
            columns={[t('landing.results.live.header', { cases: f.n(F.liveCases), runs: f.n(F.liveRuns) }), t('landing.results.live.sonnet'), t('landing.results.live.haiku')]}
            rows={[
              { label: t('landing.results.live.safe'), cells: [f.pct(F.sonnetSafe), f.pct(F.haikuSafe)] },
              { label: t('landing.results.live.recall'), cells: [f.pct(F.sonnetRecall), f.pct(F.haikuRecall)] },
              { label: t('landing.results.live.unsafeRuns'), cells: [runs([F.sonnetUnsafe.value, F.sonnetUnsafe.value, F.sonnetUnsafe.value]), runs([0, F.haikuUnsafeRun2.value, 0])], strong: true, tones: ['good'] },
              { label: t('landing.results.live.records'), cells: [f.n(F.liveRecordsToModel), f.n(F.liveRecordsToModel)] },
              { label: t('landing.results.live.latency'), cells: [`${f.n(F.sonnetP50)} / ${f.n(F.sonnetP95)} s`, `${f.n(F.haikuP50)} / ${f.n(F.haikuP95)} s`] },
              { label: t('landing.results.live.cost'), cells: [`US$ ${f.n(F.sonnetCost)}`, `US$ ${f.n(F.haikuCost)}`] },
              { label: t('landing.results.live.flips'), cells: [f.pct(F.sonnetFlips), f.pct(F.haikuFlips)] },
            ]}
          />
        </div>
        <p className="land-footnote">{t('landing.results.footnote', { date: f.date(liveRunDate.iso) })}</p>
      </div>
    </section>
  )
}
