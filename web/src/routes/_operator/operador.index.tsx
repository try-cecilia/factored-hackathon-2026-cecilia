import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_operator/operador/')({
  beforeLoad: () => {
    throw redirect({ to: '/operador/cola', replace: true })
  },
})
