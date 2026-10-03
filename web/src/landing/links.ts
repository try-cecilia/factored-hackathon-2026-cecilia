/**
 * Where the landing's links go, in one place. "Probar la demo" and "Entrar a la demo" are the one-click entry when the demo console
 * is on (DemoEntryCta, demo-entry.tsx: one click signs in as the default test customer and lands in the chat). Their address is
 * `demoEntry`, the sign-in, which lists the demo accounts when the API runs with DEMO_MODE: where they go with the console off, or
 * before the page has its script.
 */
export const demoEntry = { to: '/login' } as const
export const signInEntry = { to: '/login' } as const
export const consoleEntry = { to: '/operador/login' } as const

/**
 * The public repository of the submission. The landing never links to the private one: while the public export does not
 * exist this stays null, and the evidence grid and the limits are drawn without links. Set it and they appear.
 */
export const publicRepository: string | null = null

/** The ids of the sections the header and the footer link to. */
export const sections = {
  data: 'datos',
  architecture: 'arquitectura',
  results: 'resultados',
  console: 'consola',
  security: 'seguridad',
  operation: 'operacion',
  limits: 'limites',
  evidence: 'evidencia',
} as const
