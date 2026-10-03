/**
 * Where the landing's links go, in one place. "Probar la demo" and "Entrar a la demo" take `demoEntry`, the one-click entry's dialog
 * (`/?demo=entrar`, routes/-demo/EnterDemo.tsx), when the demo console is on; with it off they take the sign-in, which lists the demo
 * accounts when the API runs with DEMO_MODE. The landing picks one with `useDemoEntry` (demo-entry.tsx).
 */
export const demoEntry = { to: '/', search: { demo: 'entrar' } } as const
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
