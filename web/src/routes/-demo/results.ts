import type { MessageKey, Translate } from '../../i18n/translate'

/** The name of a predefined result (resolve_results of a demo case), from the texts; a code they do not name yet shows as it comes. */
export function resultLabel(t: Translate, code: string): string {
  const key = `demoMode.results.${code}` as MessageKey
  const text = t(key)
  return text === key ? code : text
}
