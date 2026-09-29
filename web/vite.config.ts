import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // Vite's .env files are not automatically copied into the server's process.env.
  const env = loadEnv(mode, process.cwd(), 'AGENT_')
  if (env.AGENT_API_URL) process.env.AGENT_API_URL ??= env.AGENT_API_URL

  return {
    clearScreen: false,
    plugins: [tanstackStart(), react()],
  }
})
