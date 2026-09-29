import { createFileRoute, redirect, useRouter } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { headTitle } from '../i18n/head'
import { useT } from '../i18n/context'
import type { MessageKey } from '../i18n/translate'
import { getDemoCustomers, getSession, login } from '../server/auth.functions'
import { PublicShell } from '../shell/PublicShell'
import { Button, QuickReplies } from '../ui'

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
    <PublicShell>
      <main className="pub__main" id="main">
        <img className="pub__mascot" src="/cecilia-avatar.png" alt="" width={96} height={96} />
        <h1>{t('login.title')}</h1>
        <p className="pub__lead">{t('login.lead')}</p>
        {motivo === 'expired' && <p className="pub__notice" role="status">{t('login.expired')}</p>}
        <form className="auth-form" onSubmit={onSubmit}>
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
          {error && <p className="pub__error" role="alert">{t(error)}</p>}
          <Button type="submit" size="lg" loading={pending}>
            {pending ? t('login.submitting') : t('login.submit')}
          </Button>
        </form>
        {demoCustomers.length > 0 && (
          <div className="pub__demo">
            <p className="pub__demo-title"><span className="badge-demo">{t('login.demoBadge')}</span>{t('login.demoAccounts')}</p>
            <QuickReplies
              label={t('login.demoAccounts')}
              options={demoCustomers.map((c) => ({ value: c.customer_id, label: c.customer_id }))}
              onSelect={(id) => {
                const account = demoCustomers.find((c) => c.customer_id === id)
                if (!account) return
                setCustomerId(account.customer_id)
                setPin(account.test_pin)
              }}
            />
          </div>
        )}
      </main>
    </PublicShell>
  )
}
