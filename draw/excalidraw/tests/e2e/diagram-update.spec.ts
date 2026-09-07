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

test('元に戻す(Undo)・やり直す(Redo)ボタンが正しく動作する', async ({ page }) => {
  // /api/chat をモックしてツールコールを返す
  await page.route('/api/chat', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reply: '図を作成しました。',
        toolCalls: [
          {
            name: 'create_view',
            args: {
              elements: [
                {
                  id: 'box1',
                  type: 'rectangle',
                  x: 100,
                  y: 100,
                  width: 140,
                  height: 70,
                  backgroundColor: '#e0e7ff',
                  strokeColor: '#3730a3',
                  label: { text: 'Start' },
                },
              ],
            },
          },
        ],
      }),
    });
  });

  await page.goto('/');

  const undoBtn = page.getByRole('button', { name: /元に戻す/ });
  const redoBtn = page.getByRole('button', { name: /やり直す/ });

  await expect(undoBtn).toBeVisible();
  await expect(redoBtn).toBeVisible();

  // 初期状態ではUndo/Redoともに無効
  await expect(undoBtn).toBeDisabled();
  await expect(redoBtn).toBeDisabled();

  // チャットで図を生成
  const textarea = page.locator('textarea');
  await textarea.fill('フローチャートを描いて');
  await page.getByRole('button', { name: '送信' }).click();

  await expect(page.getByText(/\d+ tool call/)).toBeVisible({ timeout: 10_000 });

  // 生成後はUndoが有効化される
  await expect(undoBtn).toBeEnabled({ timeout: 5_000 });
  await expect(redoBtn).toBeDisabled();

  // Undo を実行
  await undoBtn.click();
  // Undo後は Redo が有効化される
  await expect(redoBtn).toBeEnabled();

  // Redo を実行
  await redoBtn.click();
  // Redo後は Redo が再度無効化され、Undoが有効
  await expect(redoBtn).toBeDisabled();
  await expect(undoBtn).toBeEnabled();
});

test('描画中はマウスカーソルが wait になる', async ({ page }) => {
  let finishResponse: () => void = () => {};
  await page.route('/api/chat', async (route) => {
    await new Promise<void>((resolve) => {
      finishResponse = resolve;
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reply: '図を作成しました。',
        toolCalls: [],
      }),
    });
  });

  await page.goto('/');

  const body = page.locator('body');
  await expect(body).not.toHaveClass(/is-drawing/);

  const textarea = page.locator('textarea');
  await textarea.fill('システム構成図を描いて');
  await page.getByRole('button', { name: '送信' }).click();

  // 送信中・描画中は body に is-drawing が付き cursor: wait になる
  await expect(body).toHaveClass(/is-drawing/);
  const cursorStyle = await body.evaluate((el) => window.getComputedStyle(el).cursor);
  expect(cursorStyle).toBe('wait');

  // レスポンス完了
  finishResponse();

  // 完了後は is-drawing が解除される
  await expect(body).not.toHaveClass(/is-drawing/);
  const afterCursor = await body.evaluate((el) => window.getComputedStyle(el).cursor);
  expect(afterCursor).not.toBe('wait');
});



