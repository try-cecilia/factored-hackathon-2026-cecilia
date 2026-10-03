// The switches of the one-click demo, free of framework code so a plain `node --test` can run them. DEMO_MODE stays as it was (only
// '0' turns the sandbox off on the web, and the API answers 404 without it). The console demo is fail-closed: DEMO_CONSOLE must be
// exactly '1', so a service that does not set it (render.yaml, the compose) has no demo console, no bar and no one-click entry.

type Env = Record<string, string | undefined>

export const demoConsoleOn = (env: Env = process.env) => env.DEMO_CONSOLE === '1' && env.DEMO_MODE !== '0'
