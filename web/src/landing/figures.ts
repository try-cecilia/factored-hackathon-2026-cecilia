import { htmlLang, type Locale } from '../i18n/locales.ts'
import { roundHalfUp } from './rounding.ts'

/**
 * Every measured figure the landing shows, bound to the one value it comes from; `figures.test.ts` reads each source and fails
 * when that value no longer rounds to what the landing shows. Two kinds of binding:
 *  - `at`: a field of a canonical JSON report (path from the root of the file), times `scale` (100 for a rate shown as %).
 *  - `rows` + `where`: how many per-case rows of a JSON report match, e.g. the unsafe outcomes of one run.
 *  - `quote` + `pick`: a literal piece of a document or of code (English, dot decimals) and which of its numbers is the figure,
 *    counted from 0 after dropping thousands separators, times `scale`. A quote with more than one number must say which one.
 * When a report is regenerated, update the figure here: nothing else in the landing writes numbers of its own.
 */
export type JsonBinding = { source: string; at: ReadonlyArray<string | number>; scale?: number; count?: boolean }
export type QuoteBinding = { source: string; quote: string; pick?: number; scale?: number }
/** How many rows of a JSON list match every condition of `where` (a boolean condition reads a list as "not empty"). */
export type RowsBinding = { source: string; rows: ReadonlyArray<string>; where: Record<string, string | number | boolean> }
export type Figure = { value: number; digits: number } & (JsonBinding | QuoteBinding | RowsBinding)

const fig = (value: number, digits: number, source: string, quote: string, pick?: number): Figure => ({ value, digits, source, quote, pick })
const json = (value: number, digits: number, source: string, at: ReadonlyArray<string | number>, scale?: number): Figure => ({ value, digits, source, at, scale })
const rows = (value: number, source: string, list: ReadonlyArray<string>, where: Record<string, string | number | boolean>): Figure => ({ value, digits: 0, source, rows: list, where })

const README = 'README.md'
const EVALUATION = 'EVALUATION.md'
const SECURITY = 'SECURITY.md'
const LIMITATIONS = 'LIMITATIONS.md'
const ADR002 = 'docs/decisions/ADR-002-one-action-confirmed-in-code.md'
const ADR005 = 'docs/decisions/ADR-005-no-fraud-or-risk-model.md'
const ADR006 = 'docs/decisions/ADR-006-learned-classifier-beside-the-lexicon.md'
const MODEL_CARD = 'docs/MODEL_CARD.md'
const LABEL_SIGNAL = 'docs/evidence/label_signal.md'
const ASVS = 'docs/asvs-level1-checklist.md'
const OPERATIONS = 'docs/operations.md'
const RED_TEAM = 'eval/reports/RED_TEAM.md'
const LOADTEST = 'eval/reports/LOADTEST_HTTP.md'
// Canonical JSON reports.
const QUALITY = 'data/reports/quality_report.json'
const OFFLINE = 'eval/reports/system_eval.json'
const ADVERSARIAL = 'eval/reports/system_eval_adversarial.json'
const LIVE = 'eval/reports/system_eval_live.json'
const KEYWORD = ['systems', 'baseline'] as const
const IDEAL = ['systems', 'proposed (scripted)'] as const
const ADV = ['systems', 'proposed (adversarial)'] as const
const SONNET = ['systems', 'proposed (live: claude-sonnet-5)'] as const
const HAIKU = ['systems', 'proposed (live: claude-haiku-4-5)'] as const
const SAR = 'safe_automated_resolution'
// The live report keeps the per-case rows of every run, each with its `repeat` (1 to 3).
const SONNET_ROWS = ['cases', 'proposed (live: claude-sonnet-5)'] as const
const HAIKU_ROWS = ['cases', 'proposed (live: claude-haiku-4-5)'] as const

export const figures = {
  // Baseline: the organizer's contact-center data.
  contactShare: fig(35.0, 1, EVALUATION, '35.0% of 686,296 contacts', 0),
  contactsThousands: json(686, 0, QUALITY, ['tables', 'call_center_interactions', 'rows_new'], 0.001),
  humanSeconds: fig(341, 0, EVALUATION, '≈341 s (≈5.7 min)', 0),
  queueSeconds: fig(120, 0, README, '| Average handle time / wait | 221 s / 120 s |', 1),
  callSeconds: fig(221, 0, README, '| Average handle time / wait | 221 s / 120 s |', 0),
  csat: fig(2.91, 2, EVALUATION, 'CSAT is 2.91/5', 0),
  firstContact: fig(91.5, 1, README, '| First-contact resolution | 91.5% |'),
  agentHours: fig(411, 0, README, 'about 411 agent hours'),
  medianContacts: fig(6701, 0, README, 'The median is 6,701 contacts'),

  // Data: the canonical load (data/reports/quality_report.json).
  transactions: json(4425008, 0, QUALITY, ['tables', 'transactions', 'rows_new']),
  customers: json(150000, 0, QUALITY, ['tables', 'customers', 'rows_new']),
  products: json(400000, 0, QUALITY, ['tables', 'products', 'rows_new']),
  qualityTables: { value: 9, digits: 0, source: QUALITY, at: ['tables'], count: true },
  qualityChecks: json(294, 0, QUALITY, ['summary', 'checks_run']),
  qualityErrors: json(0, 0, QUALITY, ['summary', 'errors_failed']),
  qualityWarnings: json(16, 0, QUALITY, ['summary', 'warnings_failed']),
  // The share of a table's rows in quarantine that rolls its load back: the pipeline's default, as a rate.
  rollbackThreshold: { value: 1, digits: 0, source: 'data/pipeline.py', quote: 'max_quarantine_rate: float = 0.01', scale: 100 },

  // ML: the intent classifier on its test split. The keyword baseline is an upper bound (the † in EVALUATION.md).
  classifier: fig(84.7, 1, EVALUATION, '**84.7% [75.6–90.8]**', 0),
  keywordBaseline: fig(63.5, 1, EVALUATION, '63.5% [52.9–73.0]†', 0),
  classifierGain: fig(21.2, 1, EVALUATION, '+21.2 points'),
  classifierCiLow: fig(8.2, 1, EVALUATION, 'paired bootstrap 95% [+8.2, +34.1]', 1),
  classifierCiHigh: fig(34.1, 1, EVALUATION, 'paired bootstrap 95% [+8.2, +34.1]', 2),
  classifierTestCases: fig(85, 0, MODEL_CARD, '(n=85)'),
  classifierMcNemar: fig(0.0029, 4, EVALUATION, 'exact McNemar p = 0.0029'),
  // The runtime guard is the lexicon OR the classifier; the classifier alone recalls 46.7%.
  guardRecall: fig(93.3, 1, EVALUATION, '| **Lexicon OR classifier (runtime)** | **93.3%** | **0.0%** |', 0),
  guardFalseEscalations: fig(0, 0, EVALUATION, '| **Lexicon OR classifier (runtime)** | **93.3%** | **0.0%** |', 1),

  // The fraud model that was discarded: a sample of every fraud row and 300,000 legitimate ones, chronological 70/30.
  fraudAuc: fig(0.506, 3, ADR005, 'AUC **0.506**'),
  fraudTrainShare: fig(70, 0, ADR005, 'trained on the earlier 70%'),
  fraudTestShare: fig(30, 0, ADR005, 'scored on the later 30%'),
  fraudRows: fig(4316, 0, ADR005, '4,316 of'),
  fraudNegatives: fig(300000, 0, LABEL_SIGNAL, 'every fraud row and 300,000 sampled legitimate ones'),

  // Failure and regression cases: team-written, offline; what they found was fixed, so they are no longer held out.
  failureCases: fig(234, 0, EVALUATION, '0 unsafe in 234 reserved cases', 1),
  failureUnsafe: fig(0, 0, EVALUATION, '0 unsafe in 234 reserved cases', 0),

  // Architecture. The model client tries each provider this many times, then moves to the next one (render.yaml: anthropic, groq).
  attemptsPerProvider: fig(2, 0, 'agent/llm/client.py', 'max_attempts_per_provider: int = 2,'),
  // ADR-002.
  pendingMovements: fig(58234, 0, ADR002, '58,234 movements'),
  pendingShare: fig(1.99, 2, ADR002, 'Pending (1.99%)'),

  // Offline results: the 548 cases of the test split, scripted models. Safe automated resolution is over the in-scope cases.
  offlineCases: json(548, 0, OFFLINE, ['n_cases']),
  offlineEligible: json(238, 0, OFFLINE, [...KEYWORD, SAR, 'n']),
  caseTypes: json(23, 0, OFFLINE, ['n_case_types']),
  countrySegmentCells: json(12, 0, OFFLINE, ['n_cells']),
  keywordSafe: json(70.2, 1, OFFLINE, [...KEYWORD, SAR, 'rate'], 100),
  idealSafe: json(99.2, 1, OFFLINE, [...IDEAL, SAR, 'rate'], 100),
  adversarialSafe: json(60.5, 1, ADVERSARIAL, [...ADV, SAR, 'rate'], 100),
  keywordRecall: json(57.1, 1, OFFLINE, [...KEYWORD, 'escalation_recall', 'rate'], 100),
  idealRecall: json(100, 0, OFFLINE, [...IDEAL, 'escalation_recall', 'rate'], 100),
  adversarialRecall: json(100, 0, ADVERSARIAL, [...ADV, 'escalation_recall', 'rate'], 100),
  keywordMissed: json(72, 0, OFFLINE, [...KEYWORD, 'missed_escalations_n']),
  idealMissed: json(0, 0, OFFLINE, [...IDEAL, 'missed_escalations_n']),
  adversarialMissed: json(0, 0, ADVERSARIAL, [...ADV, 'missed_escalations_n']),
  keywordComplete: json(50.0, 1, OFFLINE, [...KEYWORD, 'handoff_completeness', 'rate'], 100),
  idealComplete: json(100, 0, OFFLINE, [...IDEAL, 'handoff_completeness', 'rate'], 100),
  adversarialComplete: json(100, 0, ADVERSARIAL, [...ADV, 'handoff_completeness', 'rate'], 100),
  keywordUnsafe: json(0, 0, OFFLINE, [...KEYWORD, 'unsafe_outcomes', 'k']),
  idealUnsafe: json(0, 0, OFFLINE, [...IDEAL, 'unsafe_outcomes', 'k']),
  adversarialUnsafe: json(0, 0, ADVERSARIAL, [...ADV, 'unsafe_outcomes', 'k']),
  idealRecordsToModel: json(0, 0, OFFLINE, [...IDEAL, 'records_sent_to_model', 'k']),
  adversarialRecordsToModel: json(0, 0, ADVERSARIAL, [...ADV, 'records_sent_to_model', 'k']),
  // Without the model, on the machine of the run of `offlineRunDate`: they depend on the machine.
  keywordLatencyP50: json(2.5, 1, OFFLINE, [...KEYWORD, 'latency_ms_p50']),
  keywordLatencyP95: json(10.7, 1, OFFLINE, [...KEYWORD, 'latency_ms_p95']),
  idealLatencyP50: json(5.1, 1, OFFLINE, [...IDEAL, 'latency_ms_p50']),
  idealLatencyP95: json(19.9, 1, OFFLINE, [...IDEAL, 'latency_ms_p95']),
  adversarialLatencyP50: json(5.5, 1, ADVERSARIAL, [...ADV, 'latency_ms_p50']),
  adversarialLatencyP95: json(19.7, 1, ADVERSARIAL, [...ADV, 'latency_ms_p95']),
  // Zero observed events: ≈3/n, an approximate 95% upper bound under the experiment's assumptions.
  offlineUpperBound: json(0.55, 2, OFFLINE, [...IDEAL, 'unsafe_95pct_upper_bound_if_zero'], 100),

  // Live results: a sample of 138 cases, three runs per model; the tables show run 1, except the per-run rows. Safe automated resolution is over the
  // 60 in-scope cases of the sample, not the 138.
  liveCases: json(138, 0, LIVE, ['n_cases']),
  liveRuns: json(3, 0, LIVE, [...SONNET, 'repeat_variability', 'runs']),
  liveEligible: json(60, 0, LIVE, [...SONNET, SAR, 'n']),
  sonnetSafe: json(95.0, 1, LIVE, [...SONNET, SAR, 'rate'], 100),
  sonnetSafeResolved: json(57, 0, LIVE, [...SONNET, SAR, 'k']),
  sonnetSafeLow: json(86.3, 1, LIVE, [...SONNET, SAR, 'ci95', 0], 100),
  sonnetSafeHigh: json(98.3, 1, LIVE, [...SONNET, SAR, 'ci95', 1], 100),
  haikuSafe: json(76.7, 1, LIVE, [...HAIKU, SAR, 'rate'], 100),
  haikuSafeResolved: json(46, 0, LIVE, [...HAIKU, SAR, 'k']),
  sonnetRecall: json(97.6, 1, LIVE, [...SONNET, 'escalation_recall', 'rate'], 100),
  haikuRecall: json(78.6, 1, LIVE, [...HAIKU, 'escalation_recall', 'rate'], 100),
  sonnetUnsafe: json(0, 0, LIVE, [...SONNET, 'repeat_variability', 'unsafe_outcomes', 'max']),
  // Per run, from the per-case rows of every run: unsafe outcomes, and required escalations that did not happen.
  sonnetUnsafeRun1: rows(0, LIVE, SONNET_ROWS, { repeat: 1, unsafe: true }),
  sonnetUnsafeRun2: rows(0, LIVE, SONNET_ROWS, { repeat: 2, unsafe: true }),
  sonnetUnsafeRun3: rows(0, LIVE, SONNET_ROWS, { repeat: 3, unsafe: true }),
  haikuUnsafeRun1: rows(0, LIVE, HAIKU_ROWS, { repeat: 1, unsafe: true }),
  haikuUnsafeRun2: rows(1, LIVE, HAIKU_ROWS, { repeat: 2, unsafe: true }),
  haikuUnsafeRun3: rows(0, LIVE, HAIKU_ROWS, { repeat: 3, unsafe: true }),
  sonnetMissedRun1: rows(1, LIVE, SONNET_ROWS, { repeat: 1, should_escalate: true, escalated: false }),
  sonnetMissedRun2: rows(1, LIVE, SONNET_ROWS, { repeat: 2, should_escalate: true, escalated: false }),
  sonnetMissedRun3: rows(0, LIVE, SONNET_ROWS, { repeat: 3, should_escalate: true, escalated: false }),
  haikuMissedRun1: rows(9, LIVE, HAIKU_ROWS, { repeat: 1, should_escalate: true, escalated: false }),
  haikuMissedRun2: rows(9, LIVE, HAIKU_ROWS, { repeat: 2, should_escalate: true, escalated: false }),
  haikuMissedRun3: rows(9, LIVE, HAIKU_ROWS, { repeat: 3, should_escalate: true, escalated: false }),
  sonnetRecordsToModel: json(0, 0, LIVE, [...SONNET, 'repeat_variability', 'records_sent_to_model', 'max']),
  haikuRecordsToModel: json(0, 0, LIVE, [...HAIKU, 'repeat_variability', 'records_sent_to_model', 'max']),
  sonnetP50: json(1.2, 1, LIVE, [...SONNET, 'latency_ms_p50'], 0.001),
  sonnetP95: json(2.6, 1, LIVE, [...SONNET, 'latency_ms_p95'], 0.001),
  haikuP50: json(1.0, 1, LIVE, [...HAIKU, 'latency_ms_p50'], 0.001),
  haikuP95: json(3.8, 1, LIVE, [...HAIKU, 'latency_ms_p95'], 0.001),
  sonnetCost: json(0.0034, 4, LIVE, [...SONNET, 'cost_per_safe_resolution_usd']),
  haikuCost: json(0.0080, 4, LIVE, [...HAIKU, 'cost_per_safe_resolution_usd']),
  sonnetFlips: json(2.9, 1, LIVE, [...SONNET, 'repeat_variability', 'outcome_flip_rate', 'rate'], 100),
  sonnetFlippedCases: json(4, 0, LIVE, [...SONNET, 'repeat_variability', 'outcome_flip_rate', 'k']),
  haikuFlips: json(2.9, 1, LIVE, [...HAIKU, 'repeat_variability', 'outcome_flip_rate', 'rate'], 100),
  liveUpperBound: json(2.2, 1, LIVE, [...SONNET, 'unsafe_95pct_upper_bound_if_zero'], 100),

  // A projection, not a measurement: Sonnet 5's live rate applied to the text-channel contacts.
  projectedContacts: json(955, 0, LIVE, ['projection', 'projected_monthly_automated_contacts']),
  projectedHours: json(59, 0, LIVE, ['projection', 'projected_monthly_agent_hours_saved']),
  textContacts: json(1005, 0, LIVE, ['projection', 'monthly_text_channel_contacts_measured']),
  projectedFloor: fig(705, 0, EVALUATION, 'That gives ≈705 automated per month'),

  // Ablation: offline, scripted models, variants the team built. Columns: ideal model, bad model.
  ablationNoneIdeal: fig(17.5, 1, README, '| None: a single-step chatbot with tools | 17.5% [14.6–20.9] | 74.8% [71.0–78.3] |', 1),
  ablationNoneBad: fig(74.8, 1, README, '| None: a single-step chatbot with tools | 17.5% [14.6–20.9] | 74.8% [71.0–78.3] |', 4),
  ablationIdentityIdeal: fig(13.1, 1, README, '13.1% [10.6–16.2] | 49.3% [45.1–53.4] |', 0),
  ablationIdentityBad: fig(49.3, 1, README, '13.1% [10.6–16.2] | 49.3% [45.1–53.4] |', 3),
  ablationTemplatesIdeal: fig(8.8, 1, README, '| + replies written by code | 8.8% [6.7–11.4] | 8.8% [6.7–11.4] |', 0),
  ablationTemplatesBad: fig(8.8, 1, README, '| + replies written by code | 8.8% [6.7–11.4] | 8.8% [6.7–11.4] |', 3),
  ablationAllIdeal: fig(0.0, 1, README, '| **0.0% [0.0–0.7]** | **0.0% [0.0–0.7]** |', 0),
  ablationAllBad: fig(0.0, 1, README, '| **0.0% [0.0–0.7]** | **0.0% [0.0–0.7]** |', 3),
  ablationNeedPerson: fig(48, 0, README, 'The 48 that remain before the last rung'),

  // The human red team on the deployed demo. Its length is the span of the session, 20:30 to 21:53 (figures.test.ts).
  redTeamMinutes: fig(83, 0, RED_TEAM, '30/09/2026, from 20:30 to 21:53'),
  redTeamTurns: fig(224, 0, RED_TEAM, '224 turns (3 of them on a dead session) in 42 sessions', 0),
  redTeamSessions: fig(42, 0, RED_TEAM, '224 turns (3 of them on a dead session) in 42 sessions', 2),
  redTeamCost: fig(0.44, 2, RED_TEAM, 'USD 0.44'),
  redTeamFailures: fig(0, 0, RED_TEAM, 'None of the five kinds in', 0),
  redTeamOpen: fig(10, 0, RED_TEAM, '10. **The bursts stayed under the rate limits**'),
  // Not a saturation test: the session never had more than two chats at once.
  redTeamMaxChats: fig(2, 0, RED_TEAM, 'at most 2 chats'),

  // OWASP ASVS 4.0.3 level 1: the checklist counts its rows.
  asvsTotal: fig(128, 0, ASVS, '| **Total Level 1 requirements** | **128** |', 1),
  asvsMet: fig(54, 0, ASVS, '| Implemented | 54 |'),
  asvsPartial: fig(24, 0, ASVS, '| Partial | 24 |'),
  asvsNotApplicable: fig(46, 0, ASVS, '| Not applicable | 46 |'),
  asvsMissing: fig(4, 0, ASVS, '| Limitation | 4 |'),
  pinAttempts: fig(5, 0, ASVS, '5 failed PINs lock a customer for 15 minutes', 0),
  pinLockoutMinutes: fig(15, 0, ASVS, '5 failed PINs lock a customer for 15 minutes', 1),

  // Operation: the default caps, the HTTP load test (fixture, simulated model), the deployment.
  sessionSpendCap: fig(0.25, 2, OPERATIONS, '| model spend per session | USD 0.25 |'),
  loadChatsPerSecond: fig(17.5, 1, LOADTEST, '| 17.5 | 5421.6 | 5448.7 | 5.7 |', 0),
  loadRejectMs: fig(5.7, 1, LOADTEST, '| 17.5 | 5421.6 | 5448.7 | 5.7 |', 3),
  loadSlots: fig(32, 0, LOADTEST, 'max_concurrent_chats=32'),
  loadModelMs: fig(1800, 0, LOADTEST, 'model simulated at 1800 ms'),
  instanceMemoryMb: fig(512, 0, LIMITATIONS, 'each (512 MB). What that leaves out: no replicas'),
  demoCustomers: fig(5000, 0, LIMITATIONS, 'the API loads a 5,000-customer sample'),

  // Security (SECURITY.md).
  sessionTokenBits: fig(192, 0, SECURITY, '192-bit tokens, stored hashed'),
  sessionMinutes: fig(15, 0, SECURITY, 'ends 15 minutes after it is issued'),
  roles: fig(4, 0, SECURITY, 'four separate credentials'),
} satisfies Record<string, Figure>

/** Days, as ISO dates, each with where it is written: a quote of a document or the `generated_at` of a JSON report. */
export type Day = { iso: string; source: string } & ({ quote: string } | { at: readonly string[] })
export const liveRunDate: Day = { iso: '2026-10-03', source: LIVE, at: ['generated_at'] }
export const offlineRunDate: Day = { iso: '2026-10-03', source: OFFLINE, at: ['generated_at'] }
export const redTeamDate: Day = { iso: '2026-09-30', source: RED_TEAM, quote: '30/09/2026, from 20:30 to 21:53' }
export const classifierDate: Day = { iso: '2026-10-01', source: ADR006, quote: 'accepted, recorded 2026-10-01' }

const separators: Record<Locale, { decimal: string; group: string }> = {
  es: { decimal: ',', group: '.' },
  pt: { decimal: ',', group: '.' },
}

/** `value` with `digits` decimals in the notation of `locale`, grouping thousands always ("4.316", not "4316"). */
export function formatNumber(value: number, digits: number, locale: Locale): string {
  const { decimal, group } = separators[locale]
  const [whole, fraction] = roundHalfUp(Math.abs(value), digits).split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, group)
  return `${value < 0 ? '−' : ''}${grouped}${fraction ? decimal + fraction : ''}`
}

/** The figure in the notation of `locale`. */
export const formatFigure = (figure: Figure, locale: Locale): string => formatNumber(figure.value, figure.digits, locale)

/** Millions with one decimal: 4,425,008 is "4,4". */
export const formatMillions = (figure: Figure, locale: Locale): string => formatNumber(Number(roundHalfUp(figure.value, 1, -6)), 1, locale)

/** The day in figures, as a trace line under a number writes it: "02/10/2026". */
export function formatShortDate(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(htmlLang[locale], { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T00:00:00Z`))
}

/** The day as the language writes it: "2 de octubre de 2026". */
export function formatDate(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(htmlLang[locale], { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T00:00:00Z`))
}
