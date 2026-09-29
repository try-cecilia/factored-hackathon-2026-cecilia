export type SelectAllState = 'none' | 'some' | 'all'

export function isSelected(selected: readonly string[], id: string): boolean {
  return selected.includes(id)
}

/** Adds the id when missing, removes it when present. Keeps the order of the rest. */
export function toggleId(selected: readonly string[], id: string): string[] {
  return selected.includes(id) ? selected.filter((current) => current !== id) : [...selected, id]
}

/** State of the "select all" box for the rows on screen. Selected ids that are not on screen do not count. */
export function selectAllState(visibleIds: readonly string[], selected: readonly string[]): SelectAllState {
  if (visibleIds.length === 0) return 'none'
  const chosen = new Set(selected)
  const count = visibleIds.filter((id) => chosen.has(id)).length
  return count === 0 ? 'none' : count === visibleIds.length ? 'all' : 'some'
}

/**
 * "Select all" acts on the rows on screen: unless they are all selected it selects the rest, otherwise it clears
 * them. Ids selected on other pages stay as they were.
 */
export function toggleAll(visibleIds: readonly string[], selected: readonly string[]): string[] {
  if (selectAllState(visibleIds, selected) === 'all') {
    const visible = new Set(visibleIds)
    return selected.filter((id) => !visible.has(id))
  }
  const chosen = new Set(selected)
  return [...selected, ...visibleIds.filter((id) => !chosen.has(id))]
}

/** Drops ids whose rows are gone (after a filter or a refetch), so the bulk bar never counts rows nobody can see. */
export function pruneSelection(selected: readonly string[], knownIds: readonly string[]): string[] {
  const known = new Set(knownIds)
  return selected.filter((id) => known.has(id))
}
