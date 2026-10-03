/**
 * Where the landing's links go, in one place. "Probar la demo" and "Entrar a la demo" take `demoEntry`: the one-click entry
 * is being designed, so for now it is the sign-in, which lists the demo accounts when the API runs with DEMO_MODE. When the
 * one-click entry exists, only this constant changes.
 */
export const demoEntry = { to: '/login' } as const
export const signInEntry = { to: '/login' } as const
export const consoleEntry = { to: '/operador/login' } as const

/** The ids of the sections the header and the footer link to. The landing never links to the private repository. */
export const sections = { data: 'datos', architecture: 'arquitectura', results: 'resultados', security: 'seguridad' } as const
