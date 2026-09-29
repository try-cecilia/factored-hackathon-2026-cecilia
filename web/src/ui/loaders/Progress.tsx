import { useId } from 'react'
import { useT } from '../../i18n/context'
import { SrOnly, StatusBadge } from './Marks'
import { clampPercent, connectorDone, stepStatuses } from './progressMath.ts'
import './Progress.css'

export type ProgressProps = {
  /** Names the bar. Always required for assistive tech; `hideLabel` keeps it out of the layout. */
  label: string
  /** Amount done, 0..`max`. Leave it out for an indeterminate bar (the wait has no known length). */
  value?: number
  max?: number
  /** Shows the percentage at the right of the label (determinate only). Default on. */
  showValue?: boolean
  hideLabel?: boolean
  className?: string
}

/** Determinate or indeterminate bar: a 6px pill, fill in brand blue on a tonal track. */
export function Progress({ label, value, max = 100, showValue = true, hideLabel = false, className }: ProgressProps) {
  const labelId = useId()
  const determinate = value !== undefined
  const percent = determinate ? clampPercent(value, max) : 0
  const classes = ['ui-progress', !determinate && 'ui-progress--indeterminate', className].filter(Boolean).join(' ')
  return (
    <div className={classes}>
      <div className={hideLabel ? 'ui-loader-sr' : 'ui-progress__head'}>
        <span id={labelId} className="ui-progress__label">{label}</span>
        {determinate && showValue && !hideLabel && <span className="ui-progress__value" aria-hidden="true">{percent}%</span>}
      </div>
      <div
        className="ui-progress__track"
        role="progressbar"
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={determinate ? percent : undefined}
        aria-valuetext={determinate ? `${percent}%` : undefined}
      >
        <div className="ui-progress__fill" style={determinate ? { width: `${percent}%` } : undefined} />
      </div>
    </div>
  )
}

export type ProgressStep = { id: string; label: string }

export type ProgressStepsProps = {
  steps: ProgressStep[]
  /** 0-based index of the step in progress: the ones before it are done, the ones after are pending. */
  current: number
  /** Overrides the accessible name of the list. */
  label?: string
  className?: string
}

/** Progress of a multi-part flow: numbered circles joined by connectors that fill as each part is done. */
export function ProgressSteps({ steps, current, label, className }: ProgressStepsProps) {
  const t = useT()
  const statuses = stepStatuses(steps.length, current)
  return (
    <ol className={className ? `ui-pstep ${className}` : 'ui-pstep'} role="list" aria-label={label ?? t('loaders.progress.stepsLabel')}>
      {steps.map((step, i) => {
        const status = statuses[i]
        return (
          <li key={step.id} className="ui-pstep__slot">
            {i > 0 && <span className={`ui-pstep__line${connectorDone(statuses, i - 1) ? ' ui-pstep__line--done' : ''}`} aria-hidden="true" />}
            <span className={`ui-pstep__item ui-pstep__item--${status}`} aria-current={status === 'active' ? 'step' : undefined}>
              {status === 'done' ? (
                <StatusBadge kind="success" size={20} glyph={10} stroke={2.6} />
              ) : (
                <span className="ui-pstep__num" aria-hidden="true">{i + 1}</span>
              )}
              <span>{step.label}</span>
              <SrOnly>{`, ${t(`loaders.status.${status}`)}`}</SrOnly>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
