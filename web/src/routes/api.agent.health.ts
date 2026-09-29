import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/api/agent/health')({
  server: {
    handlers: {
      GET: async () => {
        try {
          const baseUrl = process.env.AGENT_API_URL || 'http://127.0.0.1:8000'
          const response = await fetch(new URL('/health', baseUrl), {
            signal: AbortSignal.timeout(5_000),
          })
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
