import { useT } from '../../i18n/context'
import { Spinner } from '../Spinner'
import { Mascot, SrOnly, StatusBadge } from './Marks'
import type { StepStatus } from './progressMath.ts'
import './CheckingSteps.css'

export type CheckingStep = {
  id: string
  /** Already in the customer's language: it names a real lookup ("Reading August transactions"). */
  label: string
  status: StepStatus
}

export type CheckingStepsProps = {
  steps: CheckingStep[]
  /** Cecilia's mascot beside the list. Default on. */
  withAvatar?: boolean
  /** Overrides the accessible name of the list. */
  label?: string
  className?: string
}

/** The lookups Cecilia is doing, in order. A polite live list: each step that changes state is announced. */
export function CheckingSteps({ steps, withAvatar = true, label, className }: CheckingStepsProps) {
  const t = useT()
  return (
    <div className={className ? `ui-steps ${className}` : 'ui-steps'}>
      {withAvatar && <Mascot />}
      <ol className="ui-steps__list" role="list" aria-live="polite" aria-label={label ?? t('loaders.steps.label')}>
        {steps.map((step) => (
          <li key={step.id} className={`ui-steps__item ui-steps__item--${step.status}`} aria-current={step.status === 'active' ? 'step' : undefined}>
            <span className="ui-steps__marker">
              {step.status === 'done' && <StatusBadge kind="success" size={14} glyph={8} />}
              {step.status === 'failed' && <StatusBadge kind="danger" size={14} glyph={8} />}
              {step.status === 'active' && <Spinner size={14} tone="brand" />}
              {step.status === 'pending' && <span className="ui-steps__dot" aria-hidden="true" />}
            </span>
            <span>{step.label}</span>
            <SrOnly>{`, ${t(`loaders.status.${step.status}`)}`}</SrOnly>
          </li>
        ))}
      </ol>
    </div>
  )
}
