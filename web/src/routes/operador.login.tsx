import { createFileRoute, redirect, useRouter } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { getOperatorView, operatorLogin } from '../server/operator.functions'
import { sameOriginPath } from './-operator/redirect'
import operatorStylesheet from '../styles/operator.css?url'

export const Route = createFileRoute('/operador/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => {
    const target = sameOriginPath(search.redirect)
    return target ? { redirect: target } : {}
  },
  beforeLoad: async ({ search }) => {
    const view = await getOperatorView().catch(() => null)
    if (view) throw redirect({ href: search.redirect ?? '/operador/cola' })
  },
  head: () => ({
    meta: [{ title: 'Ingreso de operador · Cecilai' }, { name: 'robots', content: 'noindex' }],
    links: [{ rel: 'stylesheet', href: operatorStylesheet }],
  }),
  component: OperatorLogin,
})

const messages = {
  admin: {
    401: 'La clave de lectura no es válida.',
    429: 'Demasiados intentos. Probá de nuevo en unos minutos.',
    503: 'El servicio no está disponible o falta configurar la clave de lectura.',
  },
  operator: {
    401: 'La clave de operador no es válida.',
    429: 'Demasiados intentos. Probá de nuevo en unos minutos.',
    503: 'El servicio no está disponible o no hay claves de operador configuradas.',
  },
} as const
const unavailable = 'No se pudo completar el ingreso. Probá de nuevo.'

function OperatorLogin() {
  const { redirect: target } = Route.useSearch()
  const router = useRouter()
  const [adminKey, setAdminKey] = useState('')
  const [operatorKey, setOperatorKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      const result = await operatorLogin({ data: { admin_key: adminKey, operator_key: operatorKey } })
      if (result.ok) {
        setAdminKey('')
        setOperatorKey('')
        return await router.navigate({ href: target ?? '/operador/cola', replace: true })
      }
      setError((messages[result.key] as Record<number, string>)[result.status] ?? unavailable)
    } catch {
      setError(unavailable)
    }
    setPending(false)
  }

  return (
    <div className="op op-login">
      <main className="op-login-window">
        <a className="op-brand" href="/" aria-label="Cecilai, inicio">cecilai<span>.</span></a>
        <p className="op-eyebrow">Consola de operador</p>
        <h1>Ingresar</h1>
        <p className="op-lead">
          Con la clave de lectura ves la cola y el monitoreo. Para tomar, aprobar, rechazar o devolver casos sumá tu clave
          de operador. Ninguna llega al navegador: las guarda el servidor.
        </p>
        <form className="op-form" onSubmit={onSubmit}>
          <label>
            Clave de lectura
            <input
              name="admin_key"
              type="password"
              value={adminKey}
              onChange={(e) => setAdminKey(e.target.value)}
              required
              maxLength={200}
              autoComplete="off"
              spellCheck={false}
              aria-describedby={error ? 'op-login-error' : undefined}
            />
          </label>
          <label>
            Clave de operador <span className="op-optional">opcional</span>
            <input
              name="operator_key"
              type="password"
              value={operatorKey}
              onChange={(e) => setOperatorKey(e.target.value)}
              maxLength={200}
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          {error && <p id="op-login-error" className="op-error" role="alert">{error}</p>}
          <button className="op-button" type="submit" disabled={pending}>{pending ? 'Ingresando…' : 'Ingresar'}</button>
        </form>
      </main>
    </div>
  )
}
