import { createFileRoute } from '@tanstack/react-router'
import { handleLogout } from '../server/operator-forms'

export const Route = createFileRoute('/operador/salir')({
  server: { handlers: { POST: async () => handleLogout() } },
})
