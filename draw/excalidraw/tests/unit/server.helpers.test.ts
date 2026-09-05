import { describe, expect, it, vi, afterEach } from 'vitest';
import { fetchImageAsInlineData, createChatHandler } from '../../server';

describe('server.ts helper functions and handlers', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('content-type が image/* の画像を正しく inlineData に変換する', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'image/png; charset=utf-8' },
      arrayBuffer: async () => Buffer.from('png-data'),
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/test.png');
    expect(res).toBeTruthy();
    expect(res?.inlineData.mimeType).toBe('image/png');
    expect(res?.inlineData.data).toBe(Buffer.from('png-data').toString('base64'));
  });

  it('content-type が非画像で URL 拡張子 (.webp, .png, .jpg, .jpeg, .svg) から推測する', async () => {
    const urls = [
      { url: 'https://example.com/pic.webp', expected: 'image/webp' },
      { url: 'https://example.com/pic.png', expected: 'image/png' },
      { url: 'https://example.com/pic.jpg', expected: 'image/jpeg' },
      { url: 'https://example.com/pic.jpeg', expected: 'image/jpeg' },
      { url: 'https://example.com/pic.svg', expected: 'image/svg+xml' },
    ];

    for (const item of urls) {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: { get: () => 'application/octet-stream' },
        arrayBuffer: async () => Buffer.from('img-data'),
      } as any);

      const res = await fetchImageAsInlineData(item.url);
      expect(res?.inlineData.mimeType).toBe(item.expected);
    }
  });

  it('非画像URL (HTMLや不明な拡張子) の場合は null を返す', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'text/html' },
      arrayBuffer: async () => Buffer.from('html'),
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/page.html');
    expect(res).toBeNull();
  });

  it('HTTPレスポンスが ok でない場合は null を返す', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/notfound.png');
    expect(res).toBeNull();
  });

  it('fetch がエラーまたはタイムアウトで abort された場合は null を返す', async () => {
    global.fetch = vi.fn().mockImplementation((_, init: any) => {
      return new Promise((__, reject) => {
        if (init?.signal) {
          init.signal.addEventListener('abort', () => reject(new Error('Aborted')));
        }
      });
    });

    const res = await fetchImageAsInlineData('https://example.com/timeout.png', 10);
    expect(res).toBeNull();
  });

  it('GEMINI_MODELS 環境変数が設定されている場合のフォールバックモデル読み込み', async () => {
    const origModels = process.env.GEMINI_MODELS;
    const origKey = process.env.GEMINI_API_KEY;
    try {
      process.env.GEMINI_MODELS = ' custom-model-1, custom-model-2 ';
      process.env.GEMINI_API_KEY = 'test-key';

      let calledModel = '';
      const dummyStream = vi.fn().mockImplementation((modelName: string) => {
        calledModel = modelName;
        return (async function* () {
          yield { candidates: [{ content: { parts: [{ text: 'response' }] } }] };
        })();
      });

      const handler = createChatHandler(dummyStream as any);
      const req = {
        body: { message: 'hello' }
      } as any;
      let jsonResponse: any = null;
      const res = {
        status: vi.fn().mockReturnThis(),
        json: (data: any) => { jsonResponse = data; }
      } as any;

      await handler(req, res);
      expect(calledModel).toBe('custom-model-1');
      expect(jsonResponse.reply).toBe('response');
    } finally {
      if (origModels !== undefined) process.env.GEMINI_MODELS = origModels;
      else delete process.env.GEMINI_MODELS;
      if (origKey !== undefined) process.env.GEMINI_API_KEY = origKey;
      else delete process.env.GEMINI_API_KEY;
    }
  });

  it('ユーザーメッセージに画像URLが含まれる場合に自動で inlineData を取得してモデルに渡す', async () => {
    const origKey = process.env.GEMINI_API_KEY;
    try {
      process.env.GEMINI_API_KEY = 'test-key';

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: { get: () => 'image/png' },
        arrayBuffer: async () => Buffer.from('img-bytes'),
      } as any);

      let passedContents: any[] = [];
      const dummyStream = vi.fn().mockImplementation((_model: string, contents: any[]) => {
        passedContents = contents;
        return (async function* () {
          yield { candidates: [{ content: { parts: [{ text: 'image analyzed' }] } }] };
        })();
      });

      const handler = createChatHandler(dummyStream as any);
      const req = {
        body: { message: '図を見てください: https://example.com/diag.png' }
      } as any;
      let jsonResponse: any = null;
      const res = {
        status: vi.fn().mockReturnThis(),
        json: (data: any) => { jsonResponse = data; }
      } as any;

      await handler(req, res);
      expect(jsonResponse.reply).toBe('image analyzed');
      const lastUserContent = passedContents.find((c) => c.role === 'user');
      expect(lastUserContent.parts.length).toBe(2);
      expect(lastUserContent.parts[1].inlineData.mimeType).toBe('image/png');
    } finally {
      if (origKey !== undefined) process.env.GEMINI_API_KEY = origKey;
      else delete process.env.GEMINI_API_KEY;
    }
  });

  it('headers.get("content-type") が null の場合でも拡張子から画像形式を判定する', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => null },
      arrayBuffer: async () => Buffer.from('img-bytes'),
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/pic.png');
    expect(res?.inlineData.mimeType).toBe('image/png');
  });

  it('message が空文字列の場合および Quota exceeded エラーのリトライを処理する', async () => {
    const origKey = process.env.GEMINI_API_KEY;
    try {
      process.env.GEMINI_API_KEY = 'test-key';
      let attempts = 0;
      const dummyStream = vi.fn().mockImplementation(() => {
        attempts++;
        if (attempts === 1) {
          return (async function* () {
            yield (null as any);
            throw new Error('Quota exceeded');
          })();
        }
        return (async function* () {
          yield { candidates: [{ content: { parts: [{ text: 'retry success' }] } }] };
        })();
      });

      const handler = createChatHandler(dummyStream as any);
      const req = { body: { message: '' } } as any;
      let jsonResponse: any = null;
      const res = {
        status: vi.fn().mockReturnThis(),
        json: (data: any) => { jsonResponse = data; }
      } as any;

      await handler(req, res);
      expect(jsonResponse.reply).toBe('retry success');
    } finally {
      if (origKey !== undefined) process.env.GEMINI_API_KEY = origKey;
      else delete process.env.GEMINI_API_KEY;
    }
  });
});
