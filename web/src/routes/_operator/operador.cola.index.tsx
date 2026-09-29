import { createFileRoute } from '@tanstack/react-router'
import { Empty } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/cola/')({
  component: () => <Empty title="Elegí un caso">Vas a ver el pedido, la evidencia y las acciones disponibles.</Empty>,
})
