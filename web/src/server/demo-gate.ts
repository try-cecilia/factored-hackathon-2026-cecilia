// The switches of the one-click demo, free of framework code so a plain `node --test` can run them. The rest of the sandbox keeps
// its old rule (only DEMO_MODE='0' turns it off on the web, and the API answers 404 without it). The console demo is fail-closed:
// DEMO_MODE and DEMO_CONSOLE must both be exactly '1', so a service that does not set them has no demo console, no bar, no
// one-click entry, and none of its server functions asks the API for anything.

type Env = Record<string, string | undefined>

export const demoConsoleOn = (env: Env = process.env) => env.DEMO_MODE === '1' && env.DEMO_CONSOLE === '1'
