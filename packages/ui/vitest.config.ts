import { defineConfig } from 'vitest/config'

// Only *.spec.ts are Vitest suites.
export default defineConfig({
  test: {
    include: ['src/**/*.spec.ts'],
  },
})
