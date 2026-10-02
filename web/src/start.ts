import { createCsrfMiddleware, createStart } from '@tanstack/react-start'

// The framework installs its own CSRF middleware for server functions only while the app has no start instance, so this file stating it
// is what keeps the protection (and start.test.ts is what notices if it is dropped). Server functions are same-origin RPC: a call that
// Fetch Metadata, Origin or Referer do not prove came from this origin is a 403 before any handler runs. The operator's decisions add
// the origin check of the console's forms on top (src/server/same-origin.ts).
const csrf = createCsrfMiddleware({ filter: (ctx) => ctx.handlerType === 'serverFn' })

export const startInstance = createStart(() => ({ requestMiddleware: [csrf] }))
