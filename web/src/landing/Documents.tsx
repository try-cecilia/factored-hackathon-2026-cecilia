import type { MessageKey } from '../i18n/translate'
import { useT } from '../i18n/context'
import { figures as F, liveRunDate, redTeamDate } from './figures'
import { publicRepository, sections } from './links'
import { Eyebrow } from './parts'
import { useFigures } from './useFigures'

/** The documents behind the figures, with what each one proves. They link only to the public repository of the submission. */
export function Documents() {
  const t = useT()
  const f = useFigures()
  const docs: Array<{ id: string; path: string; meta: string }> = [
    { id: 'evaluation', path: 'EVALUATION.md', meta: t('landing.documents.evaluationMeta', { cases: f.n(F.offlineCases) }) },
    { id: 'live', path: 'eval/reports/SYSTEM_EVAL_LIVE.md', meta: t('landing.documents.liveMeta', { cases: f.n(F.liveCases), runs: f.n(F.liveRuns), date: f.shortDate(liveRunDate.iso) }) },
    { id: 'ablation', path: 'eval/reports/ABLATION.md', meta: t('landing.documents.ablationMeta', { cases: f.n(F.offlineCases) }) },
    { id: 'modelCard', path: 'docs/MODEL_CARD.md', meta: t('landing.documents.modelCardMeta', { cases: f.n(F.classifierTestCases) }) },
    { id: 'redTeam', path: 'eval/reports/RED_TEAM.md', meta: t('landing.documents.redTeamMeta', { turns: f.n(F.redTeamTurns), date: f.shortDate(redTeamDate.iso) }) },
    { id: 'security', path: 'docs/asvs-level1-checklist.md', meta: t('landing.documents.securityMeta', { total: f.n(F.asvsTotal) }) },
    { id: 'limitations', path: 'LIMITATIONS.md', meta: t('landing.documents.limitationsMeta') },
    { id: 'data', path: 'docs/data_engineering.md', meta: t('landing.documents.dataMeta', { checks: f.n(F.qualityChecks), errors: f.n(F.qualityErrors) }) },
    { id: 'decisions', path: 'docs/decisions', meta: t('landing.documents.decisionsMeta') },
  ]
  return (
    <section id={sections.evidence} className="land-sec land-documents" aria-labelledby="land-documents">
      <div className="land-in">
        <div className="land-head land-head--split">
          <div>
            <Eyebrow>{t('landing.documents.eyebrow')}</Eyebrow>
            <h2 id="land-documents" className="land-title">{t('landing.documents.title')}</h2>
          </div>
          {publicRepository && (
            <div className="land-documents__repo">
              <a className="ui-btn ui-btn--primary ui-btn--lg land-pill" href={publicRepository}>{t('landing.documents.repository')}</a>
              <p className="land-trace">{t('landing.documents.rebuild')}</p>
            </div>
          )}
        </div>
        <ul className="land-documents__grid">
          {docs.map(({ id, path, meta }) => {
            const title = t(`landing.documents.${id}` as MessageKey)
            return (
              <li key={id}>
                <h3>{publicRepository ? <a href={`${publicRepository}/blob/main/${path}`}>{title} <span aria-hidden="true">→</span></a> : title}</h3>
                <p>{t(`landing.documents.${id}Text` as MessageKey)}</p>
                <p className="land-trace">{meta}</p>
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}
