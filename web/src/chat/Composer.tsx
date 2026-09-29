import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useT } from '../i18n/context'
import { ArrowUpIcon, IconButton, QuickReplies } from '../ui'
import type { Prefill } from './ConversationProvider'

const MAX = 1000
const SUGGESTIONS = ['balance', 'recent', 'credit', 'fx', 'trace'] as const

function fit(field: HTMLTextAreaElement) {
  field.style.height = 'auto'
  field.style.height = `${Math.min(field.scrollHeight, 160)}px`
}

export type ComposerHandle = { focus: () => void }

export const Composer = forwardRef<ComposerHandle, {
  disabled: boolean
  pending: boolean
  /** Why it is disabled, in the placeholder ("No connection"). */
  hint: string | null
  showSuggestions: boolean
  onSend: (text: string) => void
  /** A text the demo panel asks the composer to hold (it is written in, with the focus and the cursor at its end). */
  prefill?: Prefill | null
  onPrefillTaken?: (seq: number) => void
}>(function Composer({ disabled, pending, hint, showSuggestions, onSend, prefill = null, onPrefillTaken }, ref) {
  const t = useT()
  const [value, setValue] = useState('')
  const input = useRef<HTMLTextAreaElement>(null)
  useImperativeHandle(ref, () => ({ focus: () => input.current?.focus() }))

  // A prefill is taken once. It goes over what was written only when the person chose it (`replace`); otherwise a draft stays.
  // The focus comes a render later (`landed`), once the text is in the field and whatever held the page inert has let go.
  const written = useRef(value)
  written.current = value
  const [landed, setLanded] = useState(0)
  useEffect(() => {
    if (!prefill) return
    if (prefill.replace || written.current.trim() === '') {
      setValue(prefill.text.slice(0, MAX))
      setLanded((n) => n + 1)
    }
    onPrefillTaken?.(prefill.seq)
  }, [prefill, onPrefillTaken])
  useEffect(() => {
    const field = input.current
    if (landed === 0 || !field) return
    fit(field)
    field.focus()
    field.setSelectionRange(field.value.length, field.value.length)
  }, [landed])

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
            fit(e.target)
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
