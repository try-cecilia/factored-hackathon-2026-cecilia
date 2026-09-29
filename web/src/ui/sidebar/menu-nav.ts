/** Keyboard logic of the row menu, kept free of the DOM so it can be tested. Indexes point into the list of items. */

export type MenuNavKey = 'ArrowDown' | 'ArrowUp' | 'Home' | 'End'

/** Where the focus goes after `key`. `enabled[i]` is false for disabled items, which are skipped. `current` is -1 when nothing has focus yet. Returns -1 if no item can take it. */
export function moveFocus(enabled: readonly boolean[], current: number, key: MenuNavKey): number {
  const count = enabled.length
  if (!enabled.some(Boolean)) return -1
  if (key === 'Home') return enabled.indexOf(true)
  if (key === 'End') return enabled.lastIndexOf(true)
  const step = key === 'ArrowDown' ? 1 : -1
  // Coming from nowhere, ArrowDown lands on the first item and ArrowUp on the last, like Home and End.
  let index = current < 0 ? (step === 1 ? -1 : count) : current
  for (let tries = 0; tries < count; tries++) {
    index = (index + step + count) % count
    if (enabled[index]) return index
  }
  return -1
}

/** Lowercase without accents, so typing "a" finds "Álbum". */
function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
}

/** Index of the item a type-ahead `query` selects, searching after `current` and wrapping; -1 if none matches. A query made of one repeated letter cycles through the items that start with it. */
export function matchTypeahead(labels: readonly string[], enabled: readonly boolean[], current: number, query: string): number {
  const needle = fold(query)
  if (!needle) return -1
  const repeated = needle.length > 1 && [...needle].every((char) => char === needle[0])
  const prefix = repeated ? needle[0] : needle
  const count = labels.length
  // A repeated letter moves on from the current item; a growing word may keep it.
  const first = repeated || current < 0 ? current + 1 : current
  for (let offset = 0; offset < count; offset++) {
    const index = (((first + offset) % count) + count) % count
    if (enabled[index] && fold(labels[index]).startsWith(prefix)) return index
  }
  return -1
}

export const TYPEAHEAD_RESET_MS = 700

/** Next type-ahead buffer: the typed character joins the previous ones unless the pause was long. Only printable single characters count. */
export function nextTypeahead(buffer: string, key: string, elapsedMs: number): string | null {
  if (key.length !== 1 || key === ' ') return null
  return elapsedMs > TYPEAHEAD_RESET_MS ? key : buffer + key
}
