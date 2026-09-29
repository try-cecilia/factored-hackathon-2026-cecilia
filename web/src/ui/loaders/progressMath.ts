// Pure helpers for the loaders: progress math and step states. No React, so node:test can run them.

export type StepStatus = 'pending' | 'active' | 'done' | 'failed'

/** Percentage 0..100 of `value` over `max`; NaN, negatives and overflow are clamped. Rounded to a whole number. */
export function clampPercent(value: number, max = 100): number {
  if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0) return 0
  return Math.round(Math.min(1, Math.max(0, value / max)) * 100)
}

export type SpinnerSize = number | 'xs' | 'sm' | 'md' | 'lg'

const NAMED_SIZES = { xs: 12, sm: 16, md: 20, lg: 28 } as const

/** The four sizes of Paper's spinner row (12, 16, 20, 28), or any pixel size. */
export function spinnerPixels(size: SpinnerSize): number {
  return typeof size === 'number' ? size : NAMED_SIZES[size]
}

/** Ring thickness in viewBox units (24): thinner on the big ring, thicker on the tiny one so it stays visible. */
export function spinnerStroke(px: number): number {
  if (px <= 10) return 3.5
  if (px >= 28) return 2.6
  return 3
}

/** Arc length as a fraction of the ring for a determinate spinner; the indeterminate one always draws 30%. */
export function spinnerArc(value: number | undefined): number {
  return value === undefined ? 0.3 : clampPercent(value) / 100
}

/** Status of every step of a stepper whose `current` step (0-based) is active: before it done, after it pending. */
export function stepStatuses(count: number, current: number): StepStatus[] {
  const active = Number.isFinite(current) ? Math.trunc(current) : 0
  return Array.from({ length: Math.max(0, count) }, (_, i): StepStatus => (i < active ? 'done' : i === active ? 'active' : 'pending'))
}

/** The connector after step `i` is filled once that step is done. */
export function connectorDone(statuses: StepStatus[], i: number): boolean {
  return statuses[i] === 'done'
}
