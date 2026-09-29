import { createFileRoute } from '@tanstack/react-router'
import { handleAddKey } from '../server/operator-forms'

export const Route = createFileRoute('/operador/clave')({
  server: { handlers: { POST: async ({ request }) => handleAddKey(request) } },
})
