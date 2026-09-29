import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// DOM tests (jsdom, Testing Library) for the components with behavior. The pure logic keeps using `node --test`
// (`src/**/*.test.ts`); these are `*.dom.test.tsx`, so the two runners never pick each other's files.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.dom.test.tsx'],
    setupFiles: ['./src/test/setup.ts'],
    // CSS imports are not processed: the tests check structure and behavior, not looks.
    css: false,
  },
})
