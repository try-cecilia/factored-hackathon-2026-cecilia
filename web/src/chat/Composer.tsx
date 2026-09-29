import { forwardRef, useImperativeHandle, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useT } from '../i18n/context'
import { ArrowUpIcon, IconButton, QuickReplies } from '../ui'

const MAX = 1000
const SUGGESTIONS = ['balance', 'recent', 'credit', 'fx', 'trace'] as const

export type ComposerHandle = { focus: () => void }

export const Composer = forwardRef<ComposerHandle, {
  disabled: boolean
  pending: boolean
  /** Why it is disabled, in the placeholder ("No connection"). */
  hint: string | null
  showSuggestions: boolean
  onSend: (text: string) => void
}>(function Composer({ disabled, pending, hint, showSuggestions, onSend }, ref) {
  const t = useT()
  const [value, setValue] = useState('')
  const input = useRef<HTMLTextAreaElement>(null)
  useImperativeHandle(ref, () => ({ focus: () => input.current?.focus() }))

  const blocked = disabled || pending
  const canSend = !blocked && value.trim().length > 0

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!canSend) return
    onSend(value.trim())
    setValue('')
    if (input.current) input.current.style.height = ''
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="composer-wrap">
      {showSuggestions && !blocked && (
        <QuickReplies
          label={t('conversation.suggestions.label')}
          options={SUGGESTIONS.map((key) => ({ value: t(`conversation.suggestions.${key}`), label: t(`conversation.suggestions.${key}`) }))}
          onSelect={onSend}
        />
      )}
      <form className="composer" onSubmit={submit} data-disabled={disabled || undefined}>
        <label className="sr-only" htmlFor="composer-input">{t('conversation.composer.label')}</label>
        <textarea
          id="composer-input"
          ref={input}
          rows={1}
          value={value}
          maxLength={MAX}
          disabled={disabled}
          placeholder={disabled && hint ? hint : t('conversation.composer.placeholder')}
          onChange={(e) => {
            setValue(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
          }}
          onKeyDown={onKeyDown}
          aria-describedby="composer-help"
        />
        <IconButton
          type="submit"
          variant="primary"
          size="md"
          label={pending ? t('conversation.composer.sending') : t('conversation.composer.send')}
          icon={<ArrowUpIcon />}
          disabled={!canSend}
        />
      </form>
      <p id="composer-help" className="composer-foot">
        {value.length > MAX - 100 ? t('conversation.composer.remaining', { n: MAX - value.length }) : t('conversation.composer.help')}
      </p>
    </div>
  )
})
