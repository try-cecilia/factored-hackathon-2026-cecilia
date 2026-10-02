import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // Vite's .env files are not automatically copied into the server's process.env.
  const env = loadEnv(mode, process.cwd(), ['AGENT_', 'WEB_', 'TRUSTED_CLIENT_IP_HEADER', 'BFF_'])
  for (const [key, value] of Object.entries(env)) process.env[key] ??= value

  return {
    clearScreen: false,
    plugins: [tanstackStart(), react()],
  }
})
