import { forwardRef, useImperativeHandle, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { SendIcon } from './icons'

const MAX = 1000

export type ComposerHandle = { focus: () => void }

export const Composer = forwardRef<ComposerHandle, {
  disabled: boolean
  pending: boolean
  hint: string | null
  suggestions: string[]
  onSend: (text: string) => void
}>(function Composer({ disabled, pending, hint, suggestions, onSend }, ref) {
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
      {suggestions.length > 0 && !blocked && (
        <ul className="chips" aria-label="Sugerencias">
          {suggestions.map((s) => (
            <li key={s}>
              <button type="button" className="chip" onClick={() => onSend(s)}>{s}</button>
            </li>
          ))}
        </ul>
      )}
      <form className="composer" onSubmit={submit} data-disabled={disabled || undefined}>
        <label className="sr-only" htmlFor="composer-input">Escribí tu mensaje para Cecilia</label>
        <textarea
          id="composer-input"
          ref={input}
          rows={1}
          value={value}
          maxLength={MAX}
          disabled={disabled}
          placeholder={disabled && hint ? hint : 'Preguntale a Cecilia por tus cuentas'}
          onChange={(e) => {
            setValue(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
          }}
          onKeyDown={onKeyDown}
          aria-describedby="composer-help"
        />
        <button type="submit" className="send" disabled={!canSend} aria-label={pending ? 'Enviando…' : 'Enviar mensaje'}>
          <SendIcon />
        </button>
      </form>
      <p id="composer-help" className="composer-foot">
        {value.length > MAX - 100
          ? `${MAX - value.length} caracteres restantes`
          : 'Enter envía, Shift+Enter agrega una línea. Cecilia puede equivocarse: revisá los datos importantes en tus resúmenes.'}
      </p>
    </div>
  )
})
