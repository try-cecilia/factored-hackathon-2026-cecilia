import { createFileRoute, redirect } from '@tanstack/react-router'
import { useT } from '../i18n/context'
import { headTitle } from '../i18n/head'
import type { MessageKey } from '../i18n/translate'
import { Button, LanguageSwitcher } from '../ui'
import { getFlash, getOperatorView, getPublicOrigins } from '../server/operator.functions'
import { sameOriginPath } from '../server/safe-path'
import operatorStylesheet from '../styles/operator.css?url'

// The closed list of reasons the URL can give for landing here; anything else is dropped, and none is ever echoed.
const motivos = ['vencida', 'sin-cookie', 'origen', 'origen-config'] as const

export const Route = createFileRoute('/operador/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string; motivo?: 'vencida' | 'sin-cookie' | 'origen' | 'origen-config' } => {
    const target = sameOriginPath(search.redirect)
    // Explicit keys, even when undefined: the router merges what a validator leaves out back in from the raw query string.
    return { redirect: target, motivo: motivos.find((m) => m === search.motivo) }
  },
  beforeLoad: async ({ search }) => {
    const view = await getOperatorView({ data: { auto: false } }).catch(() => null)
    if (view?.status === 'active') throw redirect({ href: sameOriginPath(search.redirect) ?? '/operador/cola' })
  },
  loaderDeps: ({ search }) => ({ motivo: search.motivo }),
  loader: async ({ deps }) => ({
    flash: await getFlash().catch(() => null),
    origins: deps.motivo === 'origen' ? await getPublicOrigins().catch(() => '') : '',
  }),
  head: ({ matches }) => {
    const { meta } = headTitle(matches, 'operator.pageTitle.login')
    return { meta: [...meta, { name: 'robots', content: 'noindex' }], links: [{ rel: 'stylesheet', href: operatorStylesheet }] }
  },
  component: OperatorLogin,
})

const messages: Record<string, MessageKey> = {
  admin_missing: 'operator.login.errors.admin_missing',
  session_replaced: 'operator.login.errors.session_replaced',
  key_invalid: 'operator.login.errors.key_invalid',
  admin_401: 'operator.login.errors.admin_401',
  admin_429: 'operator.login.errors.admin_429',
  admin_503: 'operator.login.errors.admin_503',
  operator_401: 'operator.login.errors.operator_401',
  operator_429: 'operator.login.errors.operator_429',
  operator_503: 'operator.login.errors.operator_503',
}

// A plain HTML form: the keys are typed into uncontrolled inputs and posted straight to the server (/operador/sesion),
// which answers with a redirect. No React state, no client request and no response ever holds them, and it works
// without JavaScript.
function OperatorLogin() {
  const t = useT()
  const { flash, origins } = Route.useLoaderData()
  const { redirect: target, motivo } = Route.useSearch()
  // A flash code (a key or a session problem the last post left) wins; else the reason in the URL. A refused origin names the origins
  // the console does trust; with none configured (development) the message is the bare one.
  const reasons = {
    'sin-cookie': 'operator.login.errors.sessionNotSaved',
    origen: origins ? 'operator.login.errors.origin_refused' : 'operator.login.errors.origin_refused_bare',
    'origen-config': 'operator.login.errors.origin_config',
  } as const
  const flashKey = flash ? (Object.hasOwn(messages, flash) ? messages[flash] : 'operator.login.errors.unavailable') : null
  const errorKey = flashKey ?? (motivo && motivo !== 'vencida' ? reasons[motivo] : null)

  return (
    <div className="op op-login">
      <main className="op-login__card" id="contenido">
        <a className="op-login__brand" href="/" aria-label={t('common.brandHome')}>
          <span className="op-login__mark"><img src="/cecilia-avatar.png" alt="" width={18} height={18} /></span>
          <span>cecilai</span>
          <span className="op-muted">{t('sidebar.brand.operations')}</span>
        </a>
        <p className="op-eyebrow">{t('operator.login.eyebrow')}</p>
        <h1>{t('operator.login.title')}</h1>
        <p className="op-lead">{t('operator.login.lead')}</p>
        {motivo === 'vencida' && !errorKey && <p className="op-banner op-banner--info" role="status">{t('operator.login.expired')}</p>}
        <form className="op-form" method="post" action="/operador/sesion" autoComplete="off">
          {target && <input type="hidden" name="redirect" value={target} />}
          <label>
            <span className="op-field-label">{t('operator.login.labelRead')}</span>
            <input className="op-input" name="admin_key" type="password" required maxLength={200} autoComplete="off" spellCheck={false} aria-describedby={errorKey ? 'op-login-error' : undefined} />
          </label>
          <label>
            <span className="op-field-label">{t('operator.login.labelOperator')} <span className="op-muted">{t('operator.login.optional')}</span></span>
            <input className="op-input" name="operator_key" type="password" maxLength={200} autoComplete="off" spellCheck={false} />
          </label>
          {errorKey && <p id="op-login-error" className="op-error" role="alert">{t(errorKey, { origins })}</p>}
          <Button type="submit" size="lg">{t('operator.login.submit')}</Button>
        </form>
        <LanguageSwitcher />
      </main>
    </div>
  )
}
