import { test, expect } from '@playwright/test';

// バックエンドは playwright.config.ts の webServer 設定で MOCK_GEMINI=1 で起動しており、
// server.ts の mockGeminiStream() が draw_dsl の functionCall を2回に分けて返す。

test('チャット送信で複数回の draw_dsl 呼び出しがすべてキャンバスへ反映される', async ({ page }) => {
  await page.goto('/');

  const textarea = page.getByPlaceholder('質問や図の作成指示を入力... (Shift+Enterで改行)');
  await textarea.fill('フローチャートを描いて');
  await page.getByRole('button', { name: '送信' }).click();

  // mockGeminiStream は draw_dsl を mock-fc-1 / mock-fc-2 の2回に分けて呼ぶ。
  // fc.id ベースの重複排除が正しく動いていれば、両方の呼び出し分がレスポンスに残り
  // 「2 tool call」と表示される（配列インデックスでの重複排除に戻ると1回に減ってしまう）。
  await expect(page.getByText(/2 tool call/)).toBeVisible({ timeout: 10_000 });

  // Excalidraw のキャンバスが描画されていることも確認する
  await expect(page.locator('canvas').first()).toBeVisible();
});
