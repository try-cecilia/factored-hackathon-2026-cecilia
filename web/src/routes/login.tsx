import { createFileRoute, redirect } from '@tanstack/react-router'
import { headTitle } from '../i18n/head'
import { getDemoCustomers, getSession, login } from '../server/auth.functions'
import { LoginForm } from './-login/LoginForm'

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

function Login() {
  const demoCustomers = Route.useLoaderData()
  const { redirect: target, motivo } = Route.useSearch()
  return <LoginForm demoCustomers={demoCustomers} target={target} expired={motivo === 'expired'} signIn={(data) => login({ data })} />
}
