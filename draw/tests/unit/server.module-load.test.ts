import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// server.ts の defaultRealCall（streamGeminiResponse の realCall 省略時のデフォルト実装）は
// 実際に ai.models.generateContentStream を呼ぶ。実ネットワークを叩かずにこの分岐を
// カバーするため、@google/genai をモックしてから動的 import する。
const generateContentStreamMock = vi.fn();

// GoogleGenAI は `new` で呼ばれるため、アロー関数ではなくクラスとしてモックする
class FakeGoogleGenAI {
  models = { generateContentStream: generateContentStreamMock };
}

vi.mock('@google/genai', () => ({
  GoogleGenAI: FakeGoogleGenAI,
}));

describe('server module load / realCall デフォルト実装', () => {
  const originalKey = process.env.GEMINI_API_KEY;
  const originalMock = process.env.MOCK_GEMINI;

  beforeEach(() => {
    // import 時点で GEMINI_API_KEY が既に設定されている状態（警告ログを出さない分岐）を再現する。
    // ESM の静的 import はファイル先頭に巻き上げられるため、動的 import を使って
    // 「env設定 → モジュール読み込み」の順序を保証している
    process.env.GEMINI_API_KEY = 'preset-key-for-coverage';
    delete process.env.MOCK_GEMINI;
    generateContentStreamMock.mockReset();
  });

  afterEach(() => {
    if (originalKey === undefined) delete process.env.GEMINI_API_KEY;
    else process.env.GEMINI_API_KEY = originalKey;
    if (originalMock === undefined) delete process.env.MOCK_GEMINI;
    else process.env.MOCK_GEMINI = originalMock;
  });

  it('GEMINI_API_KEY 設定済みの状態でモジュールを読み込める', async () => {
    const mod = await import('../../server');
    expect(mod.streamGeminiResponse).toBeTypeOf('function');
  });

  it('realCall 省略時はデフォルトで ai.models.generateContentStream を呼ぶ', async () => {
    generateContentStreamMock.mockResolvedValue(
      (async function* () {
        yield { candidates: [{ content: { parts: [{ text: 'real-api-response' }] } }] };
      })()
    );

    const mod = await import('../../server');
    const out: any[] = [];
    for await (const chunk of mod.streamGeminiResponse('gemini-x', [], {})) {
      out.push(chunk);
    }

    expect(generateContentStreamMock).toHaveBeenCalledWith({ model: 'gemini-x', contents: [], config: {} });
    expect(out[0].candidates[0].content.parts[0].text).toBe('real-api-response');
  });
});
