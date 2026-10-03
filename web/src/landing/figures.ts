import { htmlLang, type Locale } from '../i18n/locales.ts'

/**
 * Every measured figure the landing shows, with where it comes from. `source` is a path from the repository root and `quote`
 * a literal piece of that file holding the number (English, dot decimals); `figures.test.ts` reads each file and fails when the
 * quote is gone or no longer says `value`. When a report is regenerated, update the figure and its quote here: nothing else
 * in the landing writes numbers of its own.
 */
export type Figure = { value: number; digits: number; source: string; quote: string }

const fig = (value: number, digits: number, source: string, quote: string): Figure => ({ value, digits, source, quote })

const README = 'README.md'
const EVALUATION = 'EVALUATION.md'
const SECURITY = 'SECURITY.md'
const ADR002 = 'docs/decisions/ADR-002-one-action-confirmed-in-code.md'
const ADR005 = 'docs/decisions/ADR-005-no-fraud-or-risk-model.md'
// The warehouse's row counts and the data-quality run are only written in the data engineering docs.
const DATA_ENGINEERING = 'docs/data_engineering.md'
const DATA_QUALITY = 'docs/data_quality.md'

export const figures = {
  // Baseline: the organizer's contact-center data.
  contactShare: fig(35.0, 1, EVALUATION, '35.0% of 686,296 contacts'),
  contactsThousands: fig(686, 0, README, 'Share of 686 thousand contacts'),
  humanSeconds: fig(341, 0, EVALUATION, '≈341 s (≈5.7 min)'),
  queueSeconds: fig(120, 0, README, '| Average handle time / wait | 221 s / 120 s |'),
  callSeconds: fig(221, 0, README, '| Average handle time / wait | 221 s / 120 s |'),
  csat: fig(2.91, 2, EVALUATION, 'CSAT is 2.91/5'),
  firstContact: fig(91.5, 1, README, '| First-contact resolution | 91.5% |'),
  agentHours: fig(411, 0, README, 'about 411 agent hours'),
  medianContacts: fig(6701, 0, README, 'The median is 6,701 contacts'),

  // Data, ML and the language model (ADR-004 to ADR-007).
  transactions: fig(4425008, 0, ADR005, '4,425,008 transactions'),
  customers: fig(150000, 0, DATA_ENGINEERING, '150,000 customers'),
  products: fig(400000, 0, DATA_ENGINEERING, '400,000 products'),
  qualityChecks: fig(294, 0, DATA_QUALITY, '294 checks'),
  qualityErrors: fig(0, 0, DATA_QUALITY, '**0 errors'),
  rollbackThreshold: fig(1, 0, DATA_ENGINEERING, '(1% by default)'),
  classifier: fig(84.7, 1, EVALUATION, '**84.7% [75.6–90.8]**'),
  // An upper bound: two lexicon patterns were added after the test was scored (EVALUATION.md, the † under the table).
  keywordBaseline: fig(63.5, 1, EVALUATION, '63.5% [52.9–73.0]†'),
  classifierGain: fig(21.2, 1, EVALUATION, '+21.2 points'),
  classifierCiLow: fig(8.2, 1, EVALUATION, 'paired bootstrap 95% [+8.2, +34.1]'),
  classifierCiHigh: fig(34.1, 1, EVALUATION, 'paired bootstrap 95% [+8.2, +34.1]'),
  classifierMcNemar: fig(0.0029, 4, EVALUATION, 'exact McNemar p = 0.0029'),
  guardRecall: fig(93.3, 1, EVALUATION, '**93.3%** | **0.0%**'),
  guardFalseEscalations: fig(0, 0, EVALUATION, '**93.3%** | **0.0%**'),
  fraudAuc: fig(0.506, 3, ADR005, 'AUC **0.506**'),
  fraudTrainShare: fig(70, 0, ADR005, 'trained on the earlier 70%'),
  fraudTestShare: fig(30, 0, ADR005, 'scored on the later 30%'),
  fraudRows: fig(4316, 0, ADR005, '4,316 of'),
  heldoutCases: fig(234, 0, EVALUATION, '0 unsafe in 234 reserved cases'),
  heldoutUnsafe: fig(0, 0, EVALUATION, '0 unsafe in 234 reserved cases'),

  // Architecture (ADR-001, ADR-002).
  pendingMovements: fig(58234, 0, ADR002, '58,234 movements'),
  pendingShare: fig(1.99, 2, ADR002, 'Pending (1.99%)'),

  // Offline results: the 548 cases of the test split, scripted models.
  offlineCases: fig(548, 0, README, 'Offline, on the 548 cases of the test split'),
  caseTypes: fig(23, 0, README, '23 case types × 12 country·segment cells × ES/PT'),
  countrySegmentCells: fig(12, 0, README, '23 case types × 12 country·segment cells × ES/PT'),
  keywordSafe: fig(70.2, 1, README, '| Safe automated resolution | 70.2% [64.1–75.6] | 99.2% [97.0–99.8] | 60.5% [54.2–66.5] |'),
  idealSafe: fig(99.2, 1, README, '| Safe automated resolution | 70.2% [64.1–75.6] | 99.2% [97.0–99.8] | 60.5% [54.2–66.5] |'),
  adversarialSafe: fig(60.5, 1, README, '| Safe automated resolution | 70.2% [64.1–75.6] | 99.2% [97.0–99.8] | 60.5% [54.2–66.5] |'),
  keywordRecall: fig(57.1, 1, README, '| Escalation recall | 57.1% | 100% | 100% |'),
  idealRecall: fig(100, 0, README, '| Escalation recall | 57.1% | 100% | 100% |'),
  adversarialRecall: fig(100, 0, README, '| Escalation recall | 57.1% | 100% | 100% |'),
  keywordMissed: fig(72, 0, README, '| Missed escalations | 72 | 0 | 0 |'),
  idealMissed: fig(0, 0, README, '| Missed escalations | 72 | 0 | 0 |'),
  adversarialMissed: fig(0, 0, README, '| Missed escalations | 72 | 0 | 0 |'),
  keywordComplete: fig(50.0, 1, README, '| Handoff completeness | 50.0% | 100% | 100% |'),
  idealComplete: fig(100, 0, README, '| Handoff completeness | 50.0% | 100% | 100% |'),
  adversarialComplete: fig(100, 0, README, '| Handoff completeness | 50.0% | 100% | 100% |'),
  offlineUnsafe: fig(0, 0, README, '| **Unsafe outcomes** | 0 / 548 | **0 / 548** | **0 / 548** |'),
  offlineRecordsToModel: fig(0, 0, README, '| Cases that sent a customer record to the model | n/a | 0 / 548 | 0 / 548 |'),
  // Machine-dependent; EVALUATION.md keeps the run the README cites (the regenerated reports differ by machine).
  keywordLatencyP50: fig(6.5, 1, EVALUATION, '| 6.5 / 31.3 ms |'),
  keywordLatencyP95: fig(31, 0, EVALUATION, '| 6.5 / 31.3 ms |'),
  idealLatencyP50: fig(15.5, 1, EVALUATION, '| 15.5 / 60.8 ms |'),
  idealLatencyP95: fig(61, 0, EVALUATION, '| 15.5 / 60.8 ms |'),
  adversarialLatencyP50: fig(23, 0, EVALUATION, '| 23.1 / 57.7 ms |'),
  adversarialLatencyP95: fig(58, 0, EVALUATION, '| 23.1 / 57.7 ms |'),

  // Live results: 138 cases, three runs per model.
  liveCases: fig(138, 0, README, 'stratified sample of 138 of those cases'),
  liveRuns: fig(3, 0, README, '3 of each), three runs each'),
  sonnetSafe: fig(95.0, 1, README, '**95.0%** [86.3–98.3]'),
  haikuSafe: fig(78.3, 1, README, '78.3% [66.4–86.9]'),
  sonnetRecall: fig(100, 0, README, '| Escalation recall | 100% | 78.6% (9 missed) |'),
  haikuRecall: fig(78.6, 1, README, '| Escalation recall | 100% | 78.6% (9 missed) |'),
  sonnetUnsafe: fig(0, 0, README, '**0 / 138 in each run**'),
  haikuUnsafeRun2: fig(1, 0, README, '**1 / 138 in run 2**'),
  liveRecordsToModel: fig(0, 0, README, '| Cases that sent a customer record to the model | 0 / 138 in each run | 0 / 138 in each run |'),
  sonnetP50: fig(1.9, 1, README, '| Latency per case, p50 / p95 | 1.9 s / 4.2 s | 1.1 s / 4.2 s |'),
  sonnetP95: fig(4.2, 1, README, '| Latency per case, p50 / p95 | 1.9 s / 4.2 s | 1.1 s / 4.2 s |'),
  haikuP50: fig(1.1, 1, README, '| Latency per case, p50 / p95 | 1.9 s / 4.2 s | 1.1 s / 4.2 s |'),
  haikuP95: fig(4.2, 1, README, '| Latency per case, p50 / p95 | 1.9 s / 4.2 s | 1.1 s / 4.2 s |'),
  sonnetCost: fig(0.0034, 4, README, '| Model cost per safe resolution | USD 0.0034 | USD 0.0079 |'),
  haikuCost: fig(0.0079, 4, README, '| Model cost per safe resolution | USD 0.0034 | USD 0.0079 |'),
  sonnetFlips: fig(0.7, 1, README, '0.7% (1 of 138)'),
  haikuFlips: fig(2.2, 1, README, '2.2% (3 of 138)'),

  // Ablation: offline, scripted models, variants the team built.
  ablationNoneIdeal: fig(17.5, 1, README, '| None: a single-step chatbot with tools | 17.5% [14.6–20.9] | 74.8% [71.0–78.3] |'),
  ablationNoneBad: fig(74.8, 1, README, '| None: a single-step chatbot with tools | 17.5% [14.6–20.9] | 74.8% [71.0–78.3] |'),
  ablationIdentityIdeal: fig(13.1, 1, README, '13.1% [10.6–16.2] | 49.3% [45.1–53.4] |'),
  ablationIdentityBad: fig(49.3, 1, README, '13.1% [10.6–16.2] | 49.3% [45.1–53.4] |'),
  ablationTemplatesIdeal: fig(8.8, 1, README, '| + replies written by code | 8.8% [6.7–11.4] | 8.8% [6.7–11.4] |'),
  ablationTemplatesBad: fig(8.8, 1, README, '| + replies written by code | 8.8% [6.7–11.4] | 8.8% [6.7–11.4] |'),
  ablationAllIdeal: fig(0.0, 1, README, '| **0.0% [0.0–0.7]** | **0.0% [0.0–0.7]** |'),
  ablationAllBad: fig(0.0, 1, README, '| **0.0% [0.0–0.7]** | **0.0% [0.0–0.7]** |'),
  ablationNeedPerson: fig(48, 0, README, 'The 48 that remain before the last rung'),

  // A projection, not a measurement (EVALUATION.md says so in the same line).
  projectedContacts: fig(955, 0, EVALUATION, '≈955 (≈59 agent-hours)'),
  projectedHours: fig(59, 0, EVALUATION, '≈955 (≈59 agent-hours)'),

  // Security (SECURITY.md).
  sessionTokenBits: fig(192, 0, SECURITY, '192-bit tokens, stored hashed'),
  sessionMinutes: fig(15, 0, SECURITY, 'ends 15 minutes after it is issued'),
  roles: fig(4, 0, SECURITY, 'four separate credentials'),
} satisfies Record<string, Figure>

/** The day of the live runs, as an ISO date. */
export const liveRunDate = { iso: '2026-10-02', source: README, quote: 'measured on 2026-10-02' }

const separators: Record<Locale, { decimal: string; group: string }> = {
  es: { decimal: ',', group: '.' },
  pt: { decimal: ',', group: '.' },
}

/** `value` with `digits` decimals in the notation of `locale`, grouping thousands always ("4.316", not "4316"). */
export function formatNumber(value: number, digits: number, locale: Locale): string {
  const { decimal, group } = separators[locale]
  const [whole, fraction] = Math.abs(value).toFixed(digits).split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, group)
  return `${value < 0 ? '−' : ''}${grouped}${fraction ? decimal + fraction : ''}`
}

/** The figure in the notation of `locale`. */
export const formatFigure = (figure: Figure, locale: Locale): string => formatNumber(figure.value, figure.digits, locale)

/** Millions with one decimal: 4,425,008 is "4,4". */
export const formatMillions = (figure: Figure, locale: Locale): string => formatNumber(figure.value / 1e6, 1, locale)

/** The day as the language writes it: "2 de octubre de 2026". */
export function formatDate(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(htmlLang[locale], { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T00:00:00Z`))
}
