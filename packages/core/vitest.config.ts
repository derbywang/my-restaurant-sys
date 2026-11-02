import { defineConfig } from 'vitest/config'

// Only *.spec.ts are Vitest suites (src/frappe/roles.test.ts is a standalone script).
export default defineConfig({
  test: {
    include: ['src/**/*.spec.ts'],
  },
})
