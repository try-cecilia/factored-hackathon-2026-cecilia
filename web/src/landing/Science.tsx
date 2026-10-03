import type { ReactNode } from 'react'
import { useT } from '../i18n/context'
import { figures as F } from './figures'
import { sections } from './links'
import { Eyebrow } from './parts'
import { useFigures } from './useFigures'

type Card = { id: string; label: string; value: string; line: string; rows: Array<[string, ReactNode]>; conclusion: string; dark?: boolean }

/** Four learned or measured pieces, one card each: the figure, what it means, three details and what was decided. */
export function Science() {
  const t = useT()
  const f = useFigures()
  const cards: Card[] = [
    {
      id: 'data',
      label: t('landing.science.data.label'),
      value: `${f.millions(F.transactions)} M`,
      line: t('landing.science.data.line'),
      rows: [
        [t('landing.science.data.customers'), f.n(F.customers)],
        [t('landing.science.data.products'), f.n(F.products)],
        [t('landing.science.data.checks'), `${f.n(F.qualityChecks)} · ${f.n(F.qualityErrors)}`],
      ],
      conclusion: t('landing.science.data.conclusion', { threshold: f.n(F.rollbackThreshold) }),
    },
    {
      id: 'classifier',
      dark: true,
      label: t('landing.science.classifier.label'),
      value: f.pct(F.classifier),
      line: t('landing.science.classifier.line', { baseline: f.n(F.keywordBaseline) }),
      rows: [
        [t('landing.science.classifier.gain'), t('landing.science.classifier.gainValue', { gain: f.n(F.classifierGain) })],
        [t('landing.science.classifier.interval'), t('landing.science.classifier.intervalValue', { low: f.n(F.classifierCiLow), high: f.n(F.classifierCiHigh) })],
        [t('landing.science.classifier.mcnemar'), f.n(F.classifierMcNemar)],
      ],
      conclusion: t('landing.science.classifier.conclusion', { recall: f.n(F.guardRecall), falseRate: f.n(F.guardFalseEscalations) }),
    },
    {
      id: 'fraud',
      label: t('landing.science.fraud.label'),
      value: f.n(F.fraudAuc),
      line: t('landing.science.fraud.line'),
      rows: [
        [t('landing.science.fraud.model'), t('landing.science.fraud.modelValue')],
        [t('landing.science.fraud.split'), `${f.n(F.fraudTrainShare)} / ${f.n(F.fraudTestShare)}`],
        [t('landing.science.fraud.frauds'), f.n(F.fraudRows)],
      ],
      conclusion: t('landing.science.fraud.conclusion'),
    },
    {
      id: 'llm',
      label: t('landing.science.llm.label'),
      value: f.pct(F.sonnetSafe),
      line: t('landing.science.llm.line', { haiku: f.n(F.haikuSafe) }),
      rows: [
        [t('landing.science.llm.recall'), t('landing.science.llm.recallValue', { sonnet: f.n(F.sonnetRecall), haiku: f.n(F.haikuRecall) })],
        [t('landing.science.llm.cost'), t('landing.science.llm.costValue', { sonnet: f.n(F.sonnetCost), haiku: f.n(F.haikuCost) })],
        // One model call per turn: ADR-001, "One model call per turn."
        [t('landing.science.llm.calls'), '1'],
      ],
      conclusion: t('landing.science.llm.conclusion'),
    },
  ]
  return (
    <section id={sections.data} className="land-sec land-science" aria-labelledby="land-science">
      <div className="land-in">
        <div className="land-head">
          <Eyebrow>{t('landing.science.eyebrow')}</Eyebrow>
          <h2 id="land-science" className="land-title land-title--wide">{t('landing.science.title')}</h2>
        </div>
        <ul className="land-cards">
          {cards.map((card) => (
            <li key={card.id} className={card.dark ? 'land-card land-card--dark' : 'land-card'}>
              <h3 className="land-card__label">{card.label}</h3>
              <p className="land-card__figure"><strong>{card.value}</strong> <span>{card.line}</span></p>
              <dl className="land-card__rows">
                {card.rows.map(([term, value]) => (
                  <div key={term}><dt>{term}</dt><dd>{value}</dd></div>
                ))}
              </dl>
              <p className="land-card__conclusion">{card.conclusion}</p>
            </li>
          ))}
        </ul>
        <div className="land-method">
          <h3 className="land-eyebrow land-eyebrow--muted">{t('landing.science.method.title')}</h3>
          <ul className="land-method__list">
            <li><strong>{t('landing.science.method.judge')}</strong> <span>{t('landing.science.method.judgeText')}</span></li>
            <li><strong>{t('landing.science.method.heldout')}</strong> <span>{t('landing.science.method.heldoutText', { cases: f.n(F.heldoutCases) })}</span></li>
            <li><strong>{t('landing.science.method.stats')}</strong> <span>{t('landing.science.method.statsText', { runs: f.n(F.liveRuns) })}</span></li>
            <li><strong>{t('landing.science.method.tracing')}</strong> <span>{t('landing.science.method.tracingText')}</span></li>
            <li><strong>{t('landing.science.method.monitoring')}</strong> <span>{t('landing.science.method.monitoringText')}</span></li>
          </ul>
        </div>
        <p className="land-footnote">{t('landing.science.footnote', { baseline: f.n(F.keywordBaseline) })}</p>
      </div>
    </section>
  )
}
