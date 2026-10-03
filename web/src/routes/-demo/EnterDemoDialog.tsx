import { useNavigate, useRouter } from '@tanstack/react-router'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useT } from '../../i18n/context'
import type { MessageKey } from '../../i18n/translate'
import type { DemoEntry, DemoRole } from '../../server/demo-entry'
import { enterDemo, type EnterDemoResult } from '../../server/demo.functions'
import { Button } from '../../ui'
import './demo-mode.css'

type Props = {
  open: boolean
  entries: DemoEntry[]
  /** The visitor closed it without entering (the close button, Escape). An entry that worked goes to the chat instead. */
  onClose: () => void
}

type Failure = Extract<EnterDemoResult, { ok: false }>

/**
 * "Probar Cecilia como cliente" (Paper "Demo 1 · Entrar a la demo"): the visitor picks a test customer and enters with one click, no
 * PIN. A native modal dialog: the page behind is inert, the focus stays inside, and Escape closes it. Entering signs in on the server
 * (enterDemo) and lands in the chat, with the DEMO bar on top.
 */
export function EnterDemoDialog({ open, entries, onClose }: Props) {
  const t = useT()
  const router = useRouter()
  const navigate = useNavigate()
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const [role, setRole] = useState<DemoRole | null>(entries[0]?.role ?? null)
  const [entering, setEntering] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)
  const chosen = entries.some((e) => e.role === role) ? role : entries[0]?.role ?? null

  useEffect(() => {
    const node = dialog.current
    if (!node) return
    if (open && !node.open) {
      setFailure(null)
      // Where the browser has no modal dialog (an old engine, the tests' DOM), it is still shown, as a plain open dialog.
      if (typeof node.showModal === 'function') node.showModal()
      else node.setAttribute('open', '')
    } else if (!open && node.open) {
      if (typeof node.close === 'function') node.close()
      else node.removeAttribute('open')
    }
  }, [open])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!chosen || entering) return
    setEntering(true)
    setFailure(null)
    const result = await enterDemo({ data: { role: chosen } }).catch((): Failure => ({ ok: false, reason: 'failed' }))
    if (result.ok) {
      // The session (and, for the customer who speaks Portuguese, the language) changed: every loader reads again. Entering is not
      // closing: `onClose` is the visitor's cancel, and what it does (leaving the entry link) must not follow the way to the chat.
      await router.invalidate()
      await navigate({ to: '/chat' })
    } else setFailure(result)
    setEntering(false)
  }

  const error = failure && (failure.reason === 'limited' ? t('demoMode.entry.errors.limited', { seconds: failure.retryAfter ?? 60 }) : t(`demoMode.entry.errors.${failure.reason}` as MessageKey))
  return (
    <dialog ref={dialog} className="demo-dialog" aria-labelledby={titleId} onClose={onClose}>
      <form className="demo-dialog__form" onSubmit={(e) => void submit(e)}>
        <div className="demo-dialog__top">
          <span className="demo-chip demo-chip--lg">{t('demoMode.badge')}</span>
          <button type="button" className="demo-dialog__close" aria-label={t('demoMode.entry.close')} onClick={onClose}>
            <svg viewBox="0 0 20 20" width={16} height={16} aria-hidden="true" focusable="false"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" /></svg>
          </button>
        </div>
        <div className="demo-dialog__head">
          <h2 id={titleId}>{t('demoMode.entry.title')}</h2>
          <p>{t('demoMode.entry.lead')}</p>
        </div>
        {entries.length === 0 ? (
          <p className="demo-dialog__none">{t('demoMode.entry.none')}</p>
        ) : (
          <fieldset className="demo-options" disabled={entering}>
            <legend className="sr-only">{t('demoMode.entry.legend')}</legend>
            {entries.map((entry) => (
              <label key={entry.role} className="demo-option" data-checked={chosen === entry.role ? '' : undefined}>
                <input type="radio" name="demo-role" value={entry.role} checked={chosen === entry.role} onChange={() => setRole(entry.role)} />
                <span className="demo-option__text">
                  <strong>{t(`demoMode.entry.roles.${entry.role}.title`)}</strong>
                  <span>{t(`demoMode.entry.roles.${entry.role}.body`)}</span>
                </span>
              </label>
            ))}
          </fieldset>
        )}
        {error && <p className="demo-dialog__error" role="alert">{error}</p>}
        <Button type="submit" size="lg" className="demo-dialog__submit" loading={entering} disabled={!chosen}>
          {entering ? t('demoMode.entry.entering') : t('demoMode.entry.submit')}
        </Button>
        <p className="demo-dialog__note">{t('demoMode.entry.note')}</p>
      </form>
    </dialog>
  )
}
