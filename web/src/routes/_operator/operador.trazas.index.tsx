import { createFileRoute } from '@tanstack/react-router'
import { Empty } from '../-operator/ui'

export const Route = createFileRoute('/_operator/operador/trazas/')({
  component: () => <Empty title="Elegí una traza">Vas a ver qué decidió el sistema en ese turno y con qué herramientas.</Empty>,
})
