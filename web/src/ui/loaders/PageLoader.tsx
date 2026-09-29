import { useT } from '../../i18n/context'
import { Mascot } from './Marks'
import './PageLoader.css'

export type PageLoaderProps = {
  /** Text under the mascot ("Signing you in securely"). Defaults to a generic "Loading…". */
  label?: string
  /** Covers the whole viewport on the paper color. Otherwise it is a tonal panel that fills its container. */
  fullscreen?: boolean
  className?: string
}

/** A wait that owns the screen or a section: the mascot on a soft halo and one line of text. */
export function PageLoader({ label, fullscreen = false, className }: PageLoaderProps) {
  const t = useT()
  const classes = ['ui-page', fullscreen && 'ui-page--fullscreen', className].filter(Boolean).join(' ')
  return (
    <div className={classes} role="status">
      <span className="ui-page__halo" aria-hidden="true">
        <span className="ui-page__ring ui-page__ring--outer" />
        <span className="ui-page__ring ui-page__ring--inner" />
        <Mascot size={44} />
      </span>
      <span className="ui-page__label">{label ?? t('loaders.loading')}</span>
    </div>
  )
}
