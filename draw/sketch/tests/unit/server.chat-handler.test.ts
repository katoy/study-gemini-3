import { describe, expect, it, vi } from 'vitest';
import { createChatHandler } from '../../server';

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
      if (modelName === 'gemini-2.5-flash') {
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
    } finally {
      process.env.MOCK_GEMINI = origMock;
    }
  });
});
