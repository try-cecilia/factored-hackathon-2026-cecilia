import { createFileRoute } from '@tanstack/react-router'
import { handleArrival } from '../server/operator-forms'

export const Route = createFileRoute('/operador/ingreso')({
  server: { handlers: { GET: ({ request }) => handleArrival(request) } },
})
