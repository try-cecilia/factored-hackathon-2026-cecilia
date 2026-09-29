import { createFileRoute, Link, redirect, useRouter } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { ClockIcon } from '../chat/icons'
import { headTitle } from '../i18n/head'
import { useT } from '../i18n/context'
import type { MessageKey } from '../i18n/translate'
import { getDemoCustomers, getSession, login } from '../server/auth.functions'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'

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
  head: ({ matches }) => headTitle(matches, 'login.pageTitle'),
  component: Login,
})

const messages: Record<number, MessageKey> = {
  401: 'login.errors.badCredentials',
  422: 'login.errors.badCredentials',
  429: 'login.errors.tooManyAttempts',
}
const unavailable: MessageKey = 'login.errors.unavailable'

function Login() {
  const demoCustomers = Route.useLoaderData()
  const { redirect: target, motivo } = Route.useSearch()
  const router = useRouter()
  const t = useT()
  const [customerId, setCustomerId] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState<MessageKey | null>(null)
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
        <Link className="brand" to="/" aria-label={t('common.brandHome')}>
          <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
        </Link>
        <h1>{t('login.title')}</h1>
        <p className="lead">{t('login.lead')}</p>
        {motivo === 'expired' && (
          <div className="callout callout-sun" role="status">
            <ClockIcon />
            <span>{t('login.expired')}</span>
          </div>
        )}
        <form className="form" onSubmit={onSubmit}>
          <label>
            {t('login.customerId')}
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
            {t('login.pin')}
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
          {error && <p className="error" role="alert">{t(error)}</p>}
          <button className="btn btn-primary btn-lg" type="submit" disabled={pending}>
            {pending ? t('login.submitting') : t('login.submit')}
          </button>
        </form>
        {demoCustomers.length > 0 && (
          <div className="demo-accounts">
            <p className="eyebrow"><span className="badge-demo">{t('login.demoBadge')}</span> {t('login.demoAccounts')}</p>
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
        <LanguageSwitcher />
      </main>
    </div>
  )
}
