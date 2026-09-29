import './Spinner.css'
import { clampPercent, spinnerArc, spinnerPixels, spinnerStroke, type SpinnerSize } from './loaders/progressMath.ts'

/** `current` takes the text color (Button uses it); the others are Paper's tones: ink, brand blue, and white for dark fills. */
export type SpinnerTone = 'current' | 'ink' | 'brand' | 'onDark'

export type SpinnerProps = {
  /** Pixels, or Paper's row: xs 12, sm 16, md 20, lg 28. Default 14, the size inside buttons. */
  size?: SpinnerSize
  tone?: SpinnerTone
  /** 0..100 draws a determinate ring (it stops spinning); leave it out for the indeterminate one. */
  value?: number
  /** Names the spinner for assistive tech. Without it the ring is decorative, as inside a button. */
  label?: string
  className?: string
}

/** One ring: a 30% arc over a faint track. `--spinner-track` overrides the track color. */
export function Spinner({ size = 14, tone = 'current', value, label, className }: SpinnerProps) {
  const px = spinnerPixels(size)
  const stroke = spinnerStroke(px)
  const arc = spinnerArc(value)
  const determinate = value !== undefined
  const classes = ['ui-spinner', tone !== 'current' && `ui-spinner--${tone}`, determinate && 'ui-spinner--static', className]
    .filter(Boolean)
    .join(' ')
  const a11y = label
    ? {
        role: 'progressbar' as const,
        'aria-label': label,
        ...(determinate && { 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': clampPercent(value) }),
      }
    : { 'aria-hidden': true as const }
  return (
    <svg className={classes} viewBox="0 0 24 24" width={px} height={px} focusable="false" {...a11y}>
      <circle className="ui-spinner__track" cx="12" cy="12" r="9" fill="none" strokeWidth={stroke} />
      {arc > 0 && (
        <circle className="ui-spinner__arc" cx="12" cy="12" r="9" pathLength="1" fill="none" strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${arc} 1`} />
      )}
    </svg>
  )
}
