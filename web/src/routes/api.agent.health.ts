import { createFileRoute } from '@tanstack/react-router'
import { agentFetch } from '../server/agent-api'

export const Route = createFileRoute('/api/agent/health')({
  server: {
    handlers: {
      GET: async () => {
        try {
          const response = await agentFetch('/health')
          return Response.json(await response.json(), {
            status: response.status,
            headers: { 'Cache-Control': 'no-store' },
          })
        } catch {
          return Response.json({ status: 'unavailable' }, {
            status: 503,
            headers: { 'Cache-Control': 'no-store' },
          })
        }
      },
    },
  },
})
