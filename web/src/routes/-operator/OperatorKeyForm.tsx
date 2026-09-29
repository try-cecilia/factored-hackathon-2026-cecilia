import { useRouter } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { addOperatorKey } from '../../server/operator.functions'
import { explain } from './format'

/** Adds an operator key to a read-only session. The key goes to the server and is never kept in the page. */
export function OperatorKeyForm({ compact = false, onDone }: { compact?: boolean; onDone?: () => void }) {
  const router = useRouter()
  const [open, setOpen] = useState(!compact)
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      const result = await addOperatorKey({ data: { operator_key: key } })
      if (result.ok) {
        setKey('')
        await router.invalidate()
        return onDone?.()
      }
      setError(result.status === 401 ? 'La clave de operador no es válida.' : explain(result.status, true))
    } catch {
      setError('No se pudo comprobar la clave.')
    }
    setPending(false)
  }

  if (!open) return <button type="button" className="op-link" onClick={() => setOpen(true)}>Agregar clave de operador</button>
  return (
    <form className="op-inline-form" onSubmit={onSubmit}>
      <label>
        <span className={compact ? 'op-sr' : undefined}>Clave de operador</span>
        <input type="password" value={key} onChange={(e) => setKey(e.target.value)} required maxLength={200} autoComplete="off" spellCheck={false} placeholder={compact ? 'Clave de operador' : undefined} />
      </label>
      <button className="op-button op-button-small" type="submit" disabled={pending}>{pending ? 'Comprobando…' : 'Agregar'}</button>
      {error && <p className="op-error" role="alert">{error}</p>}
    </form>
  )
}
