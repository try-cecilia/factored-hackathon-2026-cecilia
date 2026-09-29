import './Marks.css'

/** Cecilia's mascot on a sky tile. Internal to the loaders; decorative, the text next to it carries the meaning. */
export function Mascot({ size = 32 }: { size?: number }) {
  return (
    <span className="ui-mascot" aria-hidden="true" style={{ width: size, height: size }}>
      <img src="/cecilia-avatar.png" alt="" width={36} height={36} />
    </span>
  )
}

/** Filled circle with a check or a cross, for done and failed. Internal to the loaders. */
export function StatusBadge({
  kind,
  size,
  glyph,
  stroke = 3,
}: {
  kind: 'success' | 'danger'
  size: number
  /** Pixel size of the check or cross inside the circle. */
  glyph: number
  stroke?: number
}) {
  return (
    <span className={`ui-badge ui-badge--${kind}`} aria-hidden="true" style={{ width: size, height: size }}>
      <svg viewBox="0 0 20 20" width={glyph} height={glyph} focusable="false">
        <path d={kind === 'success' ? 'M5 10.5l3.2 3.2L15 6.8' : 'M6 6l8 8M14 6l-8 8'} fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}

/** Text only for screen readers, so state never depends on an icon or a color. */
export function SrOnly({ children }: { children: string }) {
  return <span className="ui-loader-sr">{children}</span>
}
