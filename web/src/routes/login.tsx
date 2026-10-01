import { createFileRoute, redirect } from '@tanstack/react-router'
import { headTitle } from '../i18n/head'
import { sameOriginPath } from '../server/safe-path'
import { getDemoCustomers, getSession, login } from '../server/auth.functions'
import { LoginForm } from './-login/LoginForm'

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string; motivo?: 'expired' } => {
    // Explicit keys, even when undefined: the router merges what a validator leaves out back in from the raw query string.
    return { redirect: sameOriginPath(search.redirect), motivo: search.motivo === 'expired' ? ('expired' as const) : undefined }
  },
  beforeLoad: async ({ search }) => {
    const session = await getSession().catch(() => null)
    if (session) throw redirect({ href: sameOriginPath(search.redirect) ?? '/chat' })
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
