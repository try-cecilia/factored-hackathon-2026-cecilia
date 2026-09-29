import type { CSSProperties } from 'react'
import { useT } from '../../i18n/context'
import { SrOnly } from './Marks'
import './Skeleton.css'

type Size = number | string

/** Placeholder block. Decorative: the container that holds skeletons carries `aria-busy` and the text alternative. */
export function Skeleton({
  width,
  height = 12,
  radius,
  tone,
  className,
  style,
}: {
  width?: Size
  height?: Size
  radius?: Size
  /** Paper alternates two tones so a stack reads as loading, not empty: `muted` (default) and the fainter `subtle`. */
  tone?: 'muted' | 'subtle'
  className?: string
  style?: CSSProperties
}) {
  const classes = ['ui-skeleton', tone === 'subtle' && 'ui-skeleton--subtle', className].filter(Boolean).join(' ')
  return <span className={classes} aria-hidden="true" style={{ width, height, borderRadius: radius, ...style }} />
}

/** A chat message loading: avatar tile, a short name line and body lines. Announces "Loading" once. */
export function SkeletonMessage({ lines = 2, className }: { lines?: number; className?: string }) {
  const t = useT()
  // Paper: first line full width, second at 340/420 of it.
  const widths = ['100%', '81%']
  return (
    <div className={className ? `ui-skeleton-message ${className}` : 'ui-skeleton-message'} role="status" aria-busy="true">
      <Skeleton width={32} height={32} radius="var(--radius-control)" />
      <div className="ui-skeleton-message__body">
        <Skeleton width={80} height={10} radius="var(--radius-pill)" />
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} width={widths[i % widths.length]} height={12} radius="var(--radius-pill)" tone="subtle" />
        ))}
      </div>
      <SrOnly>{t('loaders.loading')}</SrOnly>
    </div>
  )
}

/** A small info card loading (label line over a value line), like the account summary. */
export function SkeletonCard({ width = 180, labelWidth = 90, valueWidth = 120, className }: { width?: Size; labelWidth?: Size; valueWidth?: Size; className?: string }) {
  const t = useT()
  return (
    <div className={className ? `ui-skeleton-card ${className}` : 'ui-skeleton-card'} role="status" aria-busy="true" style={{ width }}>
      <Skeleton width={labelWidth} height={9} radius="var(--radius-pill)" />
      <Skeleton width={valueWidth} height={18} radius="var(--radius-compact)" />
      <SrOnly>{t('loaders.loading')}</SrOnly>
    </div>
  )
}
