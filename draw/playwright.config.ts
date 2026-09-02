import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:3000',
  },
  webServer: [
    {
      // ルートパスに GET ハンドラが無く 404 を返すため、url ではなく port（TCP疎通のみ確認）を使う
      command: 'node --import tsx server.ts',
      port: 3001,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: 'npx vite',
      url: 'http://localhost:3000/',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
