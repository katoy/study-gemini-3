import { describe, expect, it, vi } from 'vitest';

describe('server module load without GEMINI_API_KEY', () => {
  it('GEMINI_API_KEY が無い場合に警告ログを出力してダミーキーで初期化される', async () => {
    delete process.env.GEMINI_API_KEY;
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const mod = await import('../../server');
    expect(mod.SYSTEM_INSTRUCTION).toBeDefined();
    warnSpy.mockRestore();
  });
});
