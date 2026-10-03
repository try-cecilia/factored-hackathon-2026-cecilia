import type { MessageKey, Translate } from '../../i18n/translate'
import { TAKEN_BY_OTHER } from '../../server/demo-desk-core'

/** The name of a predefined result (resolve_results of a demo case), from the texts; a code they do not name yet shows as it comes. */
export function resultLabel(t: Translate, code: string): string {
  const key = `demoMode.results.${code}` as MessageKey
  const text = t(key)
  return text === key ? code : text
}

/**
 * The one 409 whose words are known (a person of the team holds the visitor's case), said in the page's language; any other answer,
 * a version conflict included, goes on as it came, to the console's own treatment.
 */
export function withKnownConflict<R extends { ok: boolean; status?: number; message?: string }>(t: Translate, result: R): R {
  return !result.ok && result.status === 409 && result.message === TAKEN_BY_OTHER ? { ...result, message: t('demoMode.desk.takenByOther') } : result
}
