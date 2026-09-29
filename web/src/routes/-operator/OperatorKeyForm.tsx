import { useLocation } from '@tanstack/react-router'
import { useT } from '../../i18n/context'
import type { MessageKey } from '../../i18n/translate'
import { Button } from '../../ui'

const errorKeys: Record<string, MessageKey> = {
  operator_missing: 'operator.keyForm.errors.operator_missing',
  key_invalid: 'operator.keyForm.errors.key_invalid',
  operator_401: 'operator.keyForm.errors.operator_401',
  operator_429: 'operator.keyForm.errors.operator_429',
  operator_503: 'operator.keyForm.errors.operator_503',
}

/** Adds an operator key to a read-only session with a plain HTML post: the page's JavaScript never sees the key. */
export function OperatorKeyForm({ flash, compact = false }: { flash?: string | null; compact?: boolean }) {
  const t = useT()
  const { href } = useLocation()
  const errorKey = flash && Object.hasOwn(errorKeys, flash) ? errorKeys[flash] : null
  const form = (
    <form className="op-key-form" method="post" action="/operador/clave" autoComplete="off">
      <input type="hidden" name="redirect" value={href} />
      <label>
        <span className={compact ? 'sr-only' : 'op-field-label'}>{t('operator.keyForm.label')}</span>
        <input className="op-input" name="operator_key" type="password" required maxLength={200} autoComplete="off" spellCheck={false} placeholder={compact ? t('operator.keyForm.label') : undefined} />
      </label>
      <Button type="submit" size={compact ? 'xs' : 'sm'}>{t('operator.keyForm.submit')}</Button>
      {errorKey && <p className="op-error" role="alert">{t(errorKey)}</p>}
    </form>
  )
  if (!compact) return form
  return (
    <details className="op-key-toggle" open={Boolean(errorKey)}>
      <summary>{t('operator.session.addKey')}</summary>
      {form}
    </details>
  )
}
