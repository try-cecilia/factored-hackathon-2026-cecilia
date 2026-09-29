import './Spinner.css'

/** Indeterminate ring: a 30% arc over a faint track. The color is `currentColor`; `--spinner-track` overrides the track. */
export function Spinner({ size = 14, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={className ? `ui-spinner ${className}` : 'ui-spinner'}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      <circle className="ui-spinner__track" cx="12" cy="12" r="9" fill="none" strokeWidth="3" />
      <circle className="ui-spinner__arc" cx="12" cy="12" r="9" pathLength="1" fill="none" strokeWidth="3" strokeLinecap="round" strokeDasharray="0.3 1" />
    </svg>
  )
}
