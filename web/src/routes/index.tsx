import { createFileRoute, Link } from '@tanstack/react-router'

export const Route = createFileRoute('/')({ component: Home })

function Home() {
  return (
    <main>
      <a className="brand" href="/" aria-label="Cecilai, inicio">cecilai<span>.</span></a>
      <section>
        <p className="eyebrow">Próximamente</p>
        <h1>Tu espacio de<br />atención bancaria.</h1>
        <p className="description">Estamos preparando una forma más simple de consultar tus cuentas y recibir ayuda.</p>
        <Link className="button" to="/login">Ingresar</Link>
      </section>
    </main>
  )
}
