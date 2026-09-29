/** Position of the floating row menu, computed from plain rectangles so it does not need a browser to be tested. */

export type Box = { left: number; top: number; width: number; height: number }
export type Size = { width: number; height: number }

export const MENU_GAP = 6
export const VIEWPORT_MARGIN = 8

/** Opens below the trigger with the right edges aligned; flips above when it does not fit below and fits above; always stays inside the viewport. */
export function placeMenu(anchor: Box, menu: Size, viewport: Size): { left: number; top: number; placement: 'below' | 'above' } {
  const below = anchor.top + anchor.height + MENU_GAP
  const above = anchor.top - MENU_GAP - menu.height
  const fitsBelow = below + menu.height <= viewport.height - VIEWPORT_MARGIN
  const fitsAbove = above >= VIEWPORT_MARGIN
  const placement = fitsBelow || !fitsAbove ? 'below' : 'above'
  const top = clamp(placement === 'below' ? below : above, VIEWPORT_MARGIN, viewport.height - VIEWPORT_MARGIN - menu.height)
  const left = clamp(anchor.left + anchor.width - menu.width, VIEWPORT_MARGIN, viewport.width - VIEWPORT_MARGIN - menu.width)
  return { left, top, placement }
}

// max first: when the menu is taller than the viewport it is pinned to the start margin.
function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, max))
}
