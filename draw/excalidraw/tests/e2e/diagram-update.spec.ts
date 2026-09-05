import { test, expect } from '@playwright/test';

// バックエンドは playwright.config.ts の webServer 設定で MOCK_GEMINI=1 で起動しており、
// server.ts の mockGeminiStream() が draw_dsl の functionCall を2回に分けて返す。

test('チャット送信で複数回の draw_dsl 呼び出しがすべてキャンバスへ反映される', async ({ page }) => {
  await page.goto('/');

  const textarea = page.locator('textarea');
  await textarea.fill('フローチャートを描いて');
  await page.getByRole('button', { name: '送信' }).click();

  // mockGeminiStream は draw_dsl を複数回呼ぶ。
  // fc.id ベースの重複排除が正しく動いていれば、全呼び出し分がレスポンスに残り
  // 「X tool call」と表示される。
  await expect(page.getByText(/\d+ tool call/)).toBeVisible({ timeout: 15_000 });

  // Excalidraw のキャンバスが描画されていることも確認する
  await expect(page.locator('canvas').first()).toBeVisible();
});
