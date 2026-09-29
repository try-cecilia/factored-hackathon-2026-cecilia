import { useT } from '../../i18n/context'
import { Mascot, SrOnly } from './Marks'
import './ThinkingDots.css'

export type ThinkingDotsProps = {
  /** Cecilia's mascot and a pill around the dots, as it shows in the conversation. Without it: the bare dots. */
  withAvatar?: boolean
  /** Only for the dev gallery: freezes one of the three frames of the pulse. */
  frame?: 1 | 2 | 3
  /** Overrides the accessible text ("Cecilia is thinking"). */
  label?: string
  className?: string
}

/** From send until the first line arrives. Three dots that pulse; never a caret and never text that fills in. */
export function ThinkingDots({ withAvatar = false, frame, label, className }: ThinkingDotsProps) {
  const t = useT()
  const classes = ['ui-thinking', withAvatar && 'ui-thinking--avatar', className].filter(Boolean).join(' ')
  return (
    <span className={classes} role="status" data-frame={frame}>
      {withAvatar && <Mascot />}
      <span className="ui-thinking__dots" aria-hidden="true">
        <span className="ui-thinking__dot" />
        <span className="ui-thinking__dot" />
        <span className="ui-thinking__dot" />
      </span>
      <SrOnly>{label ?? t('loaders.thinking')}</SrOnly>
    </span>
  )
}
