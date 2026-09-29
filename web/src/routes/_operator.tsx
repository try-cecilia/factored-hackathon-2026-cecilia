import { createFileRoute, Link, Outlet, redirect } from '@tanstack/react-router'
import { getOperatorView } from '../server/operator.functions'
import operatorStylesheet from '../styles/operator.css?url'
import { OperatorKeyForm } from './-operator/OperatorKeyForm'
import { isAutomatic } from './-operator/refresh'

export const Route = createFileRoute('/_operator')({
  beforeLoad: async ({ location }) => {
    const view = await getOperatorView({ data: { auto: isAutomatic() } })
    if (view.status !== 'active') {
      throw redirect({ to: '/operador/login', search: { redirect: location.href, motivo: view.status === 'expired' ? 'vencida' : undefined } })
    }
    return { view }
  },
  head: () => ({
    meta: [{ name: 'robots', content: 'noindex' }],
    links: [{ rel: 'stylesheet', href: operatorStylesheet }],
  }),
  errorComponent: () => (
    <div className="op">
      <main className="op-main">
        <p className="op-notice" role="alert">La consola no está disponible en este momento.</p>
      </main>
    </div>
  ),
  component: OperatorLayout,
})

function OperatorLayout() {
  const { view } = Route.useRouteContext()
  return (
    <div className="op">
      <a className="op-skip" href="#contenido">Ir al contenido</a>
      <header className="op-bar">
        <a className="op-brand" href="/operador/cola" aria-label="Cecilai, consola de operador">cecilai<span>.</span></a>
        <nav aria-label="Consola">
          <Link to="/operador/cola" activeProps={{ 'aria-current': 'page' }}>Cola</Link>
          <Link to="/operador/monitoreo" activeProps={{ 'aria-current': 'page' }}>Monitoreo</Link>
          <Link to="/operador/trazas" activeProps={{ 'aria-current': 'page' }}>Trazas</Link>
        </nav>
        <div className="op-who">
          {view.canAct ? <span>Operador <strong>{view.operator}</strong></span> : <span className="op-chip">Solo lectura</span>}
          {!view.canAct && <OperatorKeyForm compact flash={view.flash} />}
          <form method="post" action="/operador/salir"><button type="submit" className="op-link">Salir</button></form>
        </div>
      </header>
      <main className="op-main" id="contenido" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
