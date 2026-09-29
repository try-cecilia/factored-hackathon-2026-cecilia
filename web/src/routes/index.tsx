import { createFileRoute, Link } from '@tanstack/react-router'

export const Route = createFileRoute('/')({ component: Home })

function Home() {
  return (
    <main className="home" id="main">
      <span className="brand">
        <span className="brand-mark"><img src="/cecilia-avatar.png" alt="" width={24} height={24} /></span>cecilai
      </span>
      <h1>Conocé a Cecilia,<br />tu asistente bancaria.</h1>
      <p className="lead">
        Consultá saldos, movimientos y pagos en lenguaje simple. Si hace falta una persona, Cecilia le pasa tu caso completo.
      </p>
      <Link className="btn btn-primary btn-lg" to="/login">Ingresar</Link>
    </main>
  )
}
