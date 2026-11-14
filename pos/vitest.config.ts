import { defineConfig } from 'vitest/config'

// Only *.spec.ts are Vitest suites (src/lib/category-icons.test.ts is a standalone script).
export default defineConfig({
  test: {
    include: ['src/**/*.spec.ts'],
    // the first test of a file that loads the big store imports it (several seconds when the files run side by side)
    testTimeout: 20000,
  },
})
