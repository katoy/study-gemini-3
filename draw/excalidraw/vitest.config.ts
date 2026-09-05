import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/unit/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['dsl.ts', 'server.ts', 'src/mergeServerElements.ts'],
      reporter: ['text', 'json'],
      thresholds: {
        statements: 100,
        branches: 80,
        functions: 100,
        lines: 100,
      },
    },
  },
});
