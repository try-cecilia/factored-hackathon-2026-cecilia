import { createFileRoute, Link, redirect, useRouter } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { ClockIcon } from '../chat/icons'
import { getDemoCustomers, getSession, login } from '../server/auth.functions'

function sameOriginPath(value: unknown) {
  if (typeof value !== 'string' || !value.startsWith('/')) return undefined
  const base = 'http://cecilai.invalid'
  try {
    const url = new URL(value, base)
    return url.origin === base ? url.pathname + url.search + url.hash : undefined
  } catch {
    return undefined
  }
}

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string; motivo?: 'expired' } => {
    const redirect = sameOriginPath(search.redirect)
    return { ...(redirect ? { redirect } : {}), ...(search.motivo === 'expired' ? { motivo: 'expired' as const } : {}) }
  },
  beforeLoad: async ({ search }) => {
    const session = await getSession().catch(() => null)
    if (session) throw redirect({ href: search.redirect ?? '/chat' })
  },
  loader: () => getDemoCustomers(),
  head: () => ({ meta: [{ title: 'Ingresar · Cecilai' }] }),
  component: Login,
})

const messages: Record<number, string> = {
  401: 'Número de cliente o PIN incorrectos.',
  422: 'Número de cliente o PIN incorrectos.',
  429: 'Demasiados intentos. Probá de nuevo en unos minutos.',
}
const unavailable = 'El servicio no está disponible en este momento.'

function Login() {
  const demoCustomers = Route.useLoaderData()
  const { redirect: target, motivo } = Route.useSearch()
  const router = useRouter()
  const [customerId, setCustomerId] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      const result = await login({ data: { customer_id: customerId, pin } })
      if (result.ok) return await router.navigate({ href: target ?? '/chat', replace: true })
      setError(messages[result.status] ?? unavailable)
    } catch {
      setError(unavailable)
    }
    setPending(false)
  }

  return (
    <div className="sun sun-center">
      <main className="auth-card" id="main">
        <Link className="brand" to="/" aria-label="Cecilai, inicio">
          <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
        </Link>
        <h1>Hola de nuevo.</h1>
        <p className="lead">Ingresá con tu número de cliente y tu PIN de 6 dígitos.</p>
        {motivo === 'expired' && (
          <div className="callout callout-sun" role="status">
            <ClockIcon />
            <span>Tu sesión venció. Ingresá de nuevo para continuar; la conversación empieza de cero.</span>
          </div>
        )}
        <form className="form" onSubmit={onSubmit}>
          <label>
            Número de cliente
            <input
              name="customer_id"
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              required
              minLength={3}
              maxLength={32}
              autoComplete="username"
              spellCheck={false}
            />
          </label>
          <label>
            PIN
            <input
              name="pin"
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
              required
              pattern="\d{6}"
              maxLength={6}
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn btn-primary btn-lg" type="submit" disabled={pending}>
            {pending ? 'Ingresando…' : 'Ingresar'}
          </button>
        </form>
        {demoCustomers.length > 0 && (
          <div className="demo-accounts">
            <p className="eyebrow"><span className="badge-demo">Demo</span> Cuentas de prueba</p>
            <ul>
              {demoCustomers.map((c) => (
                <li key={c.customer_id}>
                  <button type="button" className="chip" onClick={() => { setCustomerId(c.customer_id); setPin(c.test_pin) }}>
                    {c.customer_id}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  )
}
