import { useEffect, useRef, type ChangeEventHandler } from 'react'
import './RowCheckbox.css'
import { CheckIcon, DashIcon } from './icons'

type Props = {
  checked: boolean
  /** "Some rows selected" state of the select-all box. Wins over `checked` in the picture. */
  indeterminate?: boolean
  onChange: ChangeEventHandler<HTMLInputElement>
  /** The box has no text, so the accessible name is required. */
  label: string
  disabled?: boolean
  className?: string
  /** Only for the dev gallery: draws a state without needing the keyboard. */
  forceState?: 'focus'
}

/** A native checkbox drawn as a 16px square. The hit area is 28px so it is easy to hit in a 32px row. */
export function RowCheckbox({ checked, indeterminate = false, onChange, label, disabled, className, forceState }: Props) {
  const input = useRef<HTMLInputElement>(null)
  // `indeterminate` is a DOM property, not an attribute.
  useEffect(() => {
    if (input.current) input.current.indeterminate = indeterminate
  }, [indeterminate])

  return (
    <span className={className ? `ui-check ${className}` : 'ui-check'} data-state={forceState}>
      <input ref={input} type="checkbox" checked={checked} onChange={onChange} disabled={disabled} aria-label={label} />
      <span className="ui-check__box" aria-hidden="true">
        <CheckIcon className="ui-check__check" />
        <DashIcon className="ui-check__dash" />
      </span>
    </span>
  )
}
