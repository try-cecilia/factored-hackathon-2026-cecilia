import { createFileRoute, redirect } from '@tanstack/react-router'
import { getFlash, getOperatorView } from '../server/operator.functions'
import { sameOriginPath } from '../server/safe-path'
import operatorStylesheet from '../styles/operator.css?url'

export const Route = createFileRoute('/operador/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string; motivo?: 'vencida' } => {
    const target = sameOriginPath(search.redirect)
    return { ...(target && { redirect: target }), ...(search.motivo === 'vencida' && { motivo: 'vencida' as const }) }
  },
  beforeLoad: async ({ search }) => {
    const view = await getOperatorView({ data: { auto: false } }).catch(() => null)
    if (view?.status === 'active') throw redirect({ href: search.redirect ?? '/operador/cola' })
  },
  loader: () => getFlash().catch(() => null),
  head: () => ({
    meta: [{ title: 'Ingreso de operador · Cecilai' }, { name: 'robots', content: 'noindex' }],
    links: [{ rel: 'stylesheet', href: operatorStylesheet }],
  }),
  component: OperatorLogin,
})

const messages: Record<string, string> = {
  admin_missing: 'Ingresá la clave de lectura.',
  key_invalid: 'Una de las claves no es válida.',
  admin_401: 'La clave de lectura no es válida.',
  admin_429: 'Demasiados intentos. Probá de nuevo en unos minutos.',
  admin_503: 'El servicio no está disponible o falta configurar la clave de lectura.',
  operator_401: 'La clave de operador no es válida.',
  operator_429: 'Demasiados intentos. Probá de nuevo en unos minutos.',
  operator_503: 'El servicio no está disponible o no hay claves de operador configuradas.',
}
const unavailable = 'No se pudo completar el ingreso. Probá de nuevo.'

// A plain HTML form: the keys are typed into uncontrolled inputs and posted straight to the server (/operador/sesion),
// which answers with a redirect. No React state, no client request and no response ever holds them, and it works
// without JavaScript.
function OperatorLogin() {
  const flash = Route.useLoaderData()
  const { redirect: target, motivo } = Route.useSearch()
  const error = flash ? messages[flash] ?? unavailable : null

  return (
    <div className="op op-login">
      <main className="op-login-window">
        <a className="op-brand" href="/" aria-label="Cecilai, inicio">cecilai<span>.</span></a>
        <p className="op-eyebrow">Consola de operador</p>
        <h1>Ingresar</h1>
        <p className="op-lead">
          Con la clave de lectura ves la cola y el monitoreo. Para tomar, aprobar, rechazar o devolver casos sumá tu clave
          de operador. Se envían una sola vez al servidor y no se guardan ni vuelven al navegador.
        </p>
        {motivo === 'vencida' && !error && (
          <p className="op-notice op-notice-info" role="status">Tu sesión venció por inactividad. Ingresá de nuevo para seguir.</p>
        )}
        <form className="op-form" method="post" action="/operador/sesion" autoComplete="off">
          {target && <input type="hidden" name="redirect" value={target} />}
          <label>
            Clave de lectura
            <input name="admin_key" type="password" required maxLength={200} autoComplete="off" spellCheck={false} aria-describedby={error ? 'op-login-error' : undefined} />
          </label>
          <label>
            <span>Clave de operador <span className="op-optional">(opcional)</span></span>
            <input name="operator_key" type="password" maxLength={200} autoComplete="off" spellCheck={false} />
          </label>
          {error && <p id="op-login-error" className="op-error" role="alert">{error}</p>}
          <button className="op-button" type="submit">Ingresar</button>
        </form>
      </main>
    </div>
  )
}
