import type { DeskAction } from './operator.functions.ts'

// The body of an operator's action, checked on the server before it reaches the API. Free of framework code so a plain
// `node --test` can run it.
const ACTIONS: readonly DeskAction[] = ['claim', 'approve', 'reject', 'release', 'resolve']

const clean = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

export function parseDeskAction(input: unknown) {
  const { action, expected_version, reason, message } = (input ?? {}) as Record<string, unknown>
  if (!ACTIONS.includes(action as DeskAction)) throw new Error('action is not valid')
  if (expected_version !== undefined && !(Number.isInteger(expected_version) && (expected_version as number) >= 0)) throw new Error('expected_version must be an integer from 0 up')
  const note = clean(reason).slice(0, 300)
  // What the customer reads, kept on one line: the chat shows it as a line of news.
  const text = clean(message).replace(/\s+/g, ' ').slice(0, 500)
  if (action === 'resolve' && !text) throw new Error('message is required to resolve')
  return {
    action: action as DeskAction,
    expected_version: expected_version as number | undefined,
    reason: note || undefined,
    message: text || undefined,
  }
}
