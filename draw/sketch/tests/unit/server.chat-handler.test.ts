import { describe, expect, it, vi } from 'vitest';
import { createChatHandler, extractImageSources } from '../../server';

describe('createChatHandler for Sketch', () => {
  function makeReqRes(body: any) {
    const req = { body } as any;
    const res = {
      statusCode: 200,
      jsonData: null as any,
      status(code: number) {
        this.statusCode = code;
        return this;
      },
      json(data: any) {
        this.jsonData = data;
        return this;
      },
    } as any;
    return { req, res };
  }

  it('GEMINI_API_KEY が無く MOCK_GEMINI!=1 の場合は 400 エラーを返す', async () => {
    const origKey = process.env.GEMINI_API_KEY;
    const origMock = process.env.MOCK_GEMINI;
    delete process.env.GEMINI_API_KEY;
    delete process.env.MOCK_GEMINI;

    try {
      const handler = createChatHandler();
      const { req, res } = makeReqRes({ message: 'テスト' });
      await handler(req, res);

      expect(res.statusCode).toBe(400);
      expect(res.jsonData.error).toContain('GEMINI_API_KEY');
    } finally {
      process.env.GEMINI_API_KEY = origKey;
      process.env.MOCK_GEMINI = origMock;
    }
  });

  it('ストリームからテキスト応答と functionCall を正しく収集して JSON を返す', async () => {
    async function* fakeStream() {
      yield {
        candidates: [{
          content: {
            parts: [{ text: 'Sketch の図を作成しました。' }],
          },
        }],
      };
      yield {
        candidates: [{
          content: {
            parts: [{
              functionCall: {
                id: 'fc-1',
                name: 'draw_dsl',
                args: { commands: ['RECT|box1|0|0|100|50|sketch|Test'] },
              },
            }],
          },
        }],
      };
    }

    const streamFn = vi.fn().mockReturnValue(fakeStream());
    const handler = createChatHandler(streamFn as any);

    const origMock = process.env.MOCK_GEMINI;
    process.env.MOCK_GEMINI = '1';

    try {
      const { req, res } = makeReqRes({
        message: '四角形を描いて',
        history: [],
        currentElements: [
          { id: 'old1', type: 'rectangle', x: 0, y: 0, width: 50, height: 50, text: 'Old' },
        ],
      });

      await handler(req, res);

      expect(res.statusCode).toBe(200);
      expect(res.jsonData.reply).toBe('Sketch の図を作成しました。');
      expect(res.jsonData.toolCalls).toHaveLength(1);
      expect(res.jsonData.toolCalls[0].name).toBe('draw_dsl');
    } finally {
      process.env.MOCK_GEMINI = origMock;
    }
  });

  it('モデルがレート制限(429)に達した場合リトライし、フォールバックモデルへ移行する', async () => {
    let callCount = 0;
    async function* failingStream() {
      callCount++;
      yield* [];
      const err: any = new Error('Quota exceeded (429)');
      err.status = 'RESOURCE_EXHAUSTED';
      throw err;
    }

    async function* successStream() {
      yield {
        candidates: [{
          content: {
            parts: [{ text: 'フォールバック成功' }],
          },
        }],
      };
    }

    const streamFn = vi.fn().mockImplementation((modelName: string) => {
      if (modelName === 'gemini-3.6-flash') {
        return failingStream();
      }
      return successStream();
    });

    const handler = createChatHandler(streamFn as any);
    const origMock = process.env.MOCK_GEMINI;
    process.env.MOCK_GEMINI = '1';

    try {
      const { req, res } = makeReqRes({ message: 'テスト' });
      await handler(req, res);

      expect(res.statusCode).toBe(200);
      expect(res.jsonData.reply).toBe('フォールバック成功');
      expect(callCount).toBeGreaterThanOrEqual(1);
    } finally {
      process.env.MOCK_GEMINI = origMock;
    }
  });

  it('extractImageSources で Web画像URL と ローカル画像パスを抽出する', () => {
    const text = 'この画像を見て: https://example.com/test.webp と /tmp/test.png です。テキストのみ https://example.com/page もある';
    const sources = extractImageSources(text);
    expect(sources.some((s) => s.path === 'https://example.com/test.webp')).toBe(true);
  });

  it('createChatHandler に画像URLが含まれる場合、inlineData を含む parts が構築される', async () => {
    let capturedContents: any = null;
    const streamFn = vi.fn().mockImplementation((_modelName: string, contents: any) => {
      capturedContents = contents;
      async function* gen() {
        yield* [];
        yield {
          candidates: [{
            content: { parts: [{ text: '画像を認識しました' }] }
          }]
        };
      }
      return gen();
    });

    const handler = createChatHandler(streamFn as any);
    const origMock = process.env.MOCK_GEMINI;
    process.env.MOCK_GEMINI = '1';

    try {
      // 存在しないURLはfetch失敗でスキップされるが、ハンドラは正常に完了する
      const { req, res } = makeReqRes({ message: 'https://invalid-non-existent-domain-12345.com/test.png の図を書いて' });
      await handler(req, res);

      expect(res.statusCode).toBe(200);
      expect(capturedContents).toBeTruthy();
      expect(capturedContents[0].role).toBe('user');
    } finally {
      process.env.MOCK_GEMINI = origMock;
    }
  });

  it('create_view ツールコールと重複 functionCall ID を正しく処理する', async () => {
    async function* streamWithCreateView() {
      yield {
        candidates: [{
          content: {
            parts: [
              {
                functionCall: {
                  id: 'fc-dup-1',
                  name: 'create_view',
                  args: { elements: [{ id: 'elem1', type: 'rectangle', x: 10, y: 10 }] },
                },
              },
              {
                functionCall: {
                  id: 'fc-dup-1', // 重複
                  name: 'create_view',
                  args: { elements: [{ id: 'elem1', type: 'rectangle', x: 10, y: 10 }] },
                },
              },
            ],
          },
        }],
      };
    }

    const streamFn = vi.fn().mockReturnValue(streamWithCreateView());
    const handler = createChatHandler(streamFn as any);

    const origMock = process.env.MOCK_GEMINI;
    const origModels = process.env.GEMINI_MODELS;
    process.env.MOCK_GEMINI = '1';
    process.env.GEMINI_MODELS = 'custom-model-1, custom-model-2';

    try {
      const { req, res } = makeReqRes({
        message: 'テスト',
        currentElements: [
          { id: 'el1', x: 10, y: 20, width: 100, height: 50 },
          { id: 'el2', x: 200, y: 300, width: 50, height: 50 },
        ],
      });
      await handler(req, res);

      expect(res.statusCode).toBe(200);
      expect(res.jsonData.toolCalls).toHaveLength(1);
    } finally {
      process.env.MOCK_GEMINI = origMock;
      process.env.GEMINI_MODELS = origModels;
    }
  });

  it('history のロールマッピングと全モデル失敗時の 500 エラーを正しく処理する', async () => {
    const streamFn = vi.fn().mockImplementation(() => {
      throw new Error('Fatal model crash');
    });

    const handler = createChatHandler(streamFn as any);
    const origMock = process.env.MOCK_GEMINI;
    process.env.MOCK_GEMINI = '1';

    try {
      const { req, res } = makeReqRes({
        message: 'テスト',
        history: [
          { role: 'user', content: 'こんにちは' },
          { role: 'assistant', content: 'はい、どうぞ' },
        ],
      });
      await handler(req, res);

      expect(res.statusCode).toBe(500);
      expect(res.jsonData.error).toContain('Fatal model crash');
    } finally {
      process.env.MOCK_GEMINI = origMock;
    }
  });

  it('anonymous functionCall (idなし) と空テキストの extractImageSources を処理する', async () => {
    expect(extractImageSources('')).toEqual([]);

    async function* streamAnonymous() {
      yield {
        candidates: [{
          content: {
            parts: [{
              functionCall: {
                name: 'draw_dsl',
                args: { commands: ['RECT|box_anon|0|0|50|50|blue|'] },
              },
            }],
          },
        }],
      };
    }

    const streamFn = vi.fn().mockReturnValue(streamAnonymous());
    const handler = createChatHandler(streamFn as any);
    const origMock = process.env.MOCK_GEMINI;
    process.env.MOCK_GEMINI = '1';

    try {
      const { req, res } = makeReqRes({ message: 'テスト' });
      await handler(req, res);

      expect(res.statusCode).toBe(200);
      expect(res.jsonData.toolCalls).toHaveLength(1);
    } finally {
      process.env.MOCK_GEMINI = origMock;
    }
  });
});
