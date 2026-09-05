import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createChatHandler } from '../../server';

// createChatHandler が返すハンドラは (req, res) => Promise<void> の Express 互換関数。
// 実HTTPサーバーを使わず、最小限の req/res モックで直接呼び出して分岐を検証する。
function buildRes() {
  const res: any = {
    statusCode: 200,
    body: undefined as any,
    status(code: number) {
      this.statusCode = code;
      return this;
    },
    json(payload: any) {
      this.body = payload;
      return this;
    },
  };
  return res;
}

function buildReq(body: any) {
  return { body } as any;
}

type StreamFn = (modelName: string, contents: any, config: any) => AsyncGenerator<any>;

function fixedStream(chunks: any[]): StreamFn {
  return async function* () {
    for (const chunk of chunks) {
      yield chunk;
    }
  };
}

const textChunk = (text: string) => ({ candidates: [{ content: { parts: [{ text }] } }] });
const functionCallChunk = (id: string | undefined, name: string, args: any) => ({
  candidates: [{ content: { parts: [{ functionCall: { id, name, args } }] } }],
});

describe('createChatHandler', () => {
  const originalApiKey = process.env.GEMINI_API_KEY;
  const originalMock = process.env.MOCK_GEMINI;

  beforeEach(() => {
    process.env.GEMINI_API_KEY = 'test-key';
    delete process.env.MOCK_GEMINI;
  });

  afterEach(() => {
    if (originalApiKey === undefined) delete process.env.GEMINI_API_KEY;
    else process.env.GEMINI_API_KEY = originalApiKey;
    if (originalMock === undefined) delete process.env.MOCK_GEMINI;
    else process.env.MOCK_GEMINI = originalMock;
    vi.useRealTimers();
  });

  it('GEMINI_API_KEY未設定かつMOCK_GEMINIも無効なら400を返す', async () => {
    delete process.env.GEMINI_API_KEY;
    const handler = createChatHandler(fixedStream([]));
    const res = buildRes();
    await handler(buildReq({ message: 'hi', history: [], currentElements: [] }), res);
    expect(res.statusCode).toBe(400);
  });

  it('draw_dsl の functionCall を受けて200・toolCallsを返す（currentElementsあり）', async () => {
    const handler = createChatHandler(
      fixedStream([
        textChunk('説明テキスト'),
        functionCallChunk('fc-1', 'draw_dsl', { commands: ['RECT|box1|0|0|100|60|blue|A'] }),
      ])
    );
    const res = buildRes();
    await handler(
      buildReq({
        message: '図を描いて',
        history: [],
        currentElements: [{ id: 'existing', type: 'rectangle', x: 0, y: 0, width: 10, height: 10 }],
      }),
      res
    );
    expect(res.statusCode).toBe(200);
    expect(res.body.reply).toBe('説明テキスト');
    expect(res.body.toolCalls).toHaveLength(1);
  });

  it('currentElements が空でも200を返す', async () => {
    const handler = createChatHandler(fixedStream([textChunk('OK')]));
    const res = buildRes();
    await handler(buildReq({ message: 'hi', history: [], currentElements: [] }), res);
    expect(res.statusCode).toBe(200);
    expect(res.body.reply).toBe('OK');
    expect(res.body.toolCalls).toEqual([]);
  });

  it('create_view の functionCall も toolCalls に反映される', async () => {
    const handler = createChatHandler(
      fixedStream([
        functionCallChunk('fc-1', 'create_view', { elements: [{ id: 'e1', type: 'rectangle' }] }),
      ])
    );
    const res = buildRes();
    await handler(buildReq({ message: 'hi' }), res);
    expect(res.statusCode).toBe(200);
    expect(res.body.toolCalls).toEqual([
      { name: 'create_view', args: { elements: [{ id: 'e1', type: 'rectangle' }] } },
    ]);
  });

  it('コマンドが空/不正な functionCall は toolCalls に含まれない', async () => {
    const handler = createChatHandler(
      fixedStream([
        functionCallChunk('fc-1', 'draw_dsl', { commands: [] }),
        functionCallChunk('fc-2', 'unknown_tool', { foo: 'bar' }),
      ])
    );
    const res = buildRes();
    await handler(buildReq({ message: 'hi' }), res);
    expect(res.statusCode).toBe(200);
    expect(res.body.toolCalls).toEqual([]);
  });

  it('同一 fc.id の functionCall は2回目以降スキップされる', async () => {
    const handler = createChatHandler(
      fixedStream([
        functionCallChunk('dup-id', 'draw_dsl', { commands: ['RECT|box1|0|0|10|10|blue|A'] }),
        functionCallChunk('dup-id', 'draw_dsl', { commands: ['RECT|box2|0|0|10|10|blue|B'] }),
      ])
    );
    const res = buildRes();
    await handler(buildReq({ message: 'hi' }), res);
    expect(res.body.toolCalls).toHaveLength(1);
  });

  it('fc.id が無い functionCall は連番で個別に処理される', async () => {
    const handler = createChatHandler(
      fixedStream([
        functionCallChunk(undefined, 'draw_dsl', { commands: ['RECT|box1|0|0|10|10|blue|A'] }),
        functionCallChunk(undefined, 'draw_dsl', { commands: ['RECT|box2|0|0|10|10|blue|B'] }),
      ])
    );
    const res = buildRes();
    await handler(buildReq({ message: 'hi' }), res);
    expect(res.body.toolCalls).toHaveLength(2);
  });

  it('candidates が無いチャンクは無視される', async () => {
    const handler = createChatHandler(fixedStream([{}, textChunk('OK')]));
    const res = buildRes();
    await handler(buildReq({ message: 'hi' }), res);
    expect(res.statusCode).toBe(200);
    expect(res.body.reply).toBe('OK');
  });

  it('candidates はあるが content/parts が無いチャンクも無視される', async () => {
    const handler = createChatHandler(fixedStream([{ candidates: [{}] }, textChunk('OK')]));
    const res = buildRes();
    await handler(buildReq({ message: 'hi' }), res);
    expect(res.statusCode).toBe(200);
    expect(res.body.reply).toBe('OK');
  });

  it('history に複数ロールが含まれても role マッピングされる', async () => {
    const handler = createChatHandler(fixedStream([textChunk('OK')]));
    const res = buildRes();
    await handler(
      buildReq({
        message: 'hi',
        history: [
          { role: 'user', content: '前の質問' },
          { role: 'assistant', content: '前の回答' },
        ],
      }),
      res
    );
    expect(res.statusCode).toBe(200);
  });

  it('currentElements 複数件で境界ボックス計算のフォールバックも通す', async () => {
    const handler = createChatHandler(fixedStream([textChunk('OK')]));
    const res = buildRes();
    await handler(
      buildReq({
        message: 'hi',
        currentElements: [
          { id: 'e1', type: 'rectangle', x: 50, y: 50, width: 100, height: 50, text: 'A' },
          // width/height 省略でデフォルト値フォールバックを通す。かつ既存の min を更新するが max は更新しない
          { id: 'e2', type: 'rectangle', x: 10, y: 10 },
          // 既存の min/max を更新しない（false分岐用）
          { id: 'e3', type: 'rectangle', x: 100, y: 100, width: 10, height: 10 },
        ],
      }),
      res
    );
    expect(res.statusCode).toBe(200);
  });

  it('プロンプト構築中に Error でない値が投げられても500・デフォルトメッセージになる', async () => {
    const handler = createChatHandler(fixedStream([]));
    const res = buildRes();
    await handler(
      buildReq({
        message: 'hi',
        currentElements: [
          {
            id: 'e1',
            type: 'text',
            x: 0,
            y: 0,
            width: 10,
            height: 10,
            get text(): string {
              // eslint非対象。message プロパティを持たない値を意図的に throw する
              throw 'boom';
            },
          },
        ],
      }),
      res
    );
    expect(res.statusCode).toBe(500);
    expect(res.body.error).toBe('Internal Server Error');
  });

  it('429エラーはリトライ後に成功する', async () => {
    vi.useFakeTimers();
    let calls = 0;
    const streamFn: StreamFn = async function* () {
      calls += 1;
      if (calls === 1) {
        const err: any = new Error('429 Too Many Requests');
        throw err;
      }
      yield textChunk('リトライ成功');
    };
    const handler = createChatHandler(streamFn);
    const res = buildRes();
    const done = handler(buildReq({ message: 'hi' }), res);
    await vi.advanceTimersByTimeAsync(3000);
    await done;
    expect(res.statusCode).toBe(200);
    expect(res.body.reply).toBe('リトライ成功');
    expect(calls).toBe(2);
  });

  it('429エラーが retries 回続くモデルはフォールバック先モデルで成功する', async () => {
    vi.useFakeTimers();
    const streamFn: StreamFn = async function* (modelName) {
      if (modelName === 'gemini-3.5-flash') {
        const err: any = new Error('429 rate limited');
        throw err;
      }
      yield textChunk(`成功: ${modelName}`);
    };
    const handler = createChatHandler(streamFn);
    const res = buildRes();
    const done = handler(buildReq({ message: 'hi' }), res);
    await vi.advanceTimersByTimeAsync(5000);
    await done;
    expect(res.statusCode).toBe(200);
    expect(res.body.reply).toBe('成功: gemini-3.7-flash');
  });

  it('全モデルが失敗すると500を返す', async () => {
    vi.useFakeTimers();
    // StreamFn型に合わせるためジェネレータにしているが、即座にthrowする意図的な実装（yield無し）
    // oxlint-disable-next-line require-yield
    const streamFn: StreamFn = async function* () {
      const err: any = new Error('429 always rate limited');
      throw err;
    };
    const handler = createChatHandler(streamFn);
    const res = buildRes();
    const done = handler(buildReq({ message: 'hi' }), res);
    await vi.advanceTimersByTimeAsync(20000);
    await done;
    expect(res.statusCode).toBe(500);
    expect(res.body.error).toContain('全モデルの呼び出しに失敗しました');
  });

  it('429以外のエラーはリトライせず即座に次モデルへフォールバックする', async () => {
    const streamFn: StreamFn = async function* (modelName) {
      if (modelName === 'gemini-3.5-flash') {
        throw new Error('unexpected failure');
      }
      yield textChunk(`成功: ${modelName}`);
    };
    const handler = createChatHandler(streamFn);
    const res = buildRes();
    await handler(buildReq({ message: 'hi' }), res);
    expect(res.statusCode).toBe(200);
    expect(res.body.reply).toBe('成功: gemini-3.7-flash');
  });

  it('ユーザーメッセージに画像URLが含まれている場合、画像を取得して parts に追加する', async () => {
    let capturedContents: any = null;
    const streamFn: StreamFn = async function* (_model, contents) {
      capturedContents = contents;
      yield textChunk('画像を認識しました');
    };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'image/png' }),
      arrayBuffer: async () => Buffer.from('mock-png-data'),
    } as any);

    try {
      const handler = createChatHandler(streamFn);
      const res = buildRes();
      await handler(
        buildReq({
          message: 'https://example.com/test.png の図を書いて',
        }),
        res
      );

      expect(res.statusCode).toBe(200);
      expect(capturedContents).toBeDefined();
      const userMessage = capturedContents.find((c: any) => c.role === 'user');
      expect(userMessage.parts).toHaveLength(2);
      expect(userMessage.parts[1]).toMatchObject({
        inlineData: {
          mimeType: 'image/png',
          data: Buffer.from('mock-png-data').toString('base64'),
        },
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('画像fetchが失敗した場合はエラーにならずテキストのみで継続する', async () => {
    let capturedContents: any = null;
    const streamFn: StreamFn = async function* (_model, contents) {
      capturedContents = contents;
      yield textChunk('テキストで回答');
    };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    try {
      const handler = createChatHandler(streamFn);
      const res = buildRes();
      await handler(
        buildReq({
          message: 'https://example.com/fail.png の図を書いて',
        }),
        res
      );

      expect(res.statusCode).toBe(200);
      expect(capturedContents).toBeDefined();
      const userMessage = capturedContents.find((c: any) => c.role === 'user');
      expect(userMessage.parts).toHaveLength(1);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
