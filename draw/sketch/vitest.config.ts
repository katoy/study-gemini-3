import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/unit/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['dsl.ts', 'server.ts', 'src/mergeServerElements.ts'],
      thresholds: {
        statements: 85,
        branches: 60,
        functions: 70,
        lines: 85,
      },
    },
  },
});
