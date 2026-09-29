import { useLocation } from '@tanstack/react-router'

const messages: Record<string, string> = {
  operator_missing: 'Ingresá la clave de operador.',
  key_invalid: 'La clave de operador no es válida.',
  operator_401: 'La clave de operador no es válida.',
  operator_429: 'Demasiados intentos fallidos desde este origen. Esperá un minuto.',
  operator_503: 'No hay claves de operador configuradas o el servicio no está disponible.',
}

/** Adds an operator key to a read-only session with a plain HTML post: the page's JavaScript never sees the key. */
export function OperatorKeyForm({ flash, compact = false }: { flash?: string | null; compact?: boolean }) {
  const { href } = useLocation()
  const error = flash && flash in messages ? messages[flash] : null
  const form = (
    <form className="op-inline-form" method="post" action="/operador/clave" autoComplete="off">
      <input type="hidden" name="redirect" value={href} />
      <label>
        <span className={compact ? 'op-sr' : undefined}>Clave de operador</span>
        <input name="operator_key" type="password" required maxLength={200} autoComplete="off" spellCheck={false} placeholder={compact ? 'Clave de operador' : undefined} />
      </label>
      <button className="op-button op-button-small" type="submit">Agregar</button>
      {error && <p className="op-error" role="alert">{error}</p>}
    </form>
  )
  if (!compact) return form
  return (
    <details className="op-key-toggle" open={Boolean(error)}>
      <summary className="op-link">Agregar clave de operador</summary>
      {form}
    </details>
  )
}
