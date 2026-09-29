import { createFileRoute } from '@tanstack/react-router'
import { handleLogin } from '../server/operator-forms'

export const Route = createFileRoute('/operador/sesion')({
  server: { handlers: { POST: async ({ request }) => handleLogin(request) } },
})
