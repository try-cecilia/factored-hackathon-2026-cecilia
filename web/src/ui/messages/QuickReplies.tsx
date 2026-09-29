import './QuickReplies.css'

export type QuickReply = {
  value: string
  label: string
  /** Only for the dev gallery: draws a state without the pointer or the keyboard. */
  forceState?: 'hover' | 'focus'
}

export type QuickRepliesProps = {
  options: QuickReply[]
  onSelect?: (value: string) => void
  /** The option already chosen. It stays highlighted and the others stop answering. */
  selectedValue?: string
  disabled?: boolean
  /** Names the group for assistive tech; already translated by the caller. */
  label: string
  className?: string
}

/** Row of chips that fill in a reply in one tap (clarify options, decline suggestions). */
export function QuickReplies({ options, onSelect, selectedValue, disabled, label, className }: QuickRepliesProps) {
  const locked = disabled || selectedValue !== undefined
  return (
    <div className={className ? `ui-quick ${className}` : 'ui-quick'} role="group" aria-label={label}>
      {options.map((option) => {
        const selected = option.value === selectedValue
        return (
          <button
            key={option.value}
            type="button"
            className="ui-quick__chip"
            data-state={option.forceState}
            aria-pressed={selectedValue === undefined ? undefined : selected}
            disabled={locked && !selected}
            onClick={locked ? undefined : () => onSelect?.(option.value)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
